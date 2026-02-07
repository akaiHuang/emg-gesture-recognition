"""
動作記錄模組：同步記錄 EMG 訊號、攝影機影像與手部骨架

此模組提供 EMG 訊號與視覺資料的同步記錄功能，用於建立訓練資料集。

主要功能：
1. MediaPipe 手部關鍵點追蹤（21 個關鍵點）
2. EMG 訊號與影像時間戳同步
3. 資料儲存（.npz 格式）與影片輸出（.mp4）
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

import cv2
import numpy as np

# 延遲載入 MediaPipe，避免拖慢啟動速度
# MediaPipe import 會觸發 matplotlib 字體掃描（在 macOS 上很慢）
if TYPE_CHECKING:
    import mediapipe as mp

MEDIAPIPE_AVAILABLE = False
_mp_module = None
_mp_loading = False  # 標記是否正在載入


def _lazy_import_mediapipe():
    """延遲載入 MediaPipe（只在需要時載入）
    
    此函數會同步載入 MediaPipe，可能需要 15+ 秒（首次載入）
    建議使用 _async_import_mediapipe() 在背景載入
    """
    global MEDIAPIPE_AVAILABLE, _mp_module, _mp_loading
    if _mp_module is None and not _mp_loading:
        _mp_loading = True
        try:
            import mediapipe as mp
            _mp_module = mp
            MEDIAPIPE_AVAILABLE = True
            print("✅ MediaPipe 載入完成")
        except ImportError:
            print("⚠️ MediaPipe 未安裝，手部追蹤功能將不可用")
            print("   安裝指令: pip install mediapipe")
            MEDIAPIPE_AVAILABLE = False
        finally:
            _mp_loading = False
    return _mp_module


async def _async_import_mediapipe():
    """在背景非同步載入 MediaPipe
    
    Returns:
        bool: 是否載入成功
    """
    import asyncio
    global MEDIAPIPE_AVAILABLE, _mp_module, _mp_loading
    
    if _mp_module is not None:
        return True  # 已經載入
    
    if _mp_loading:
        # 已經在載入中，等待完成
        while _mp_loading:
            await asyncio.sleep(0.1)
        return MEDIAPIPE_AVAILABLE
    
    _mp_loading = True
    print("🔄 開始在背景載入 MediaPipe（這可能需要 10-15 秒）...")
    
    def _load_in_thread():
        """在執行緒中載入 MediaPipe"""
        try:
            import mediapipe as mp
            return mp, True
        except ImportError as e:
            print(f"❌ MediaPipe 載入失敗: {e}")
            return None, False
    
    # 在執行緒池中載入（避免阻塞事件循環）
    loop = asyncio.get_event_loop()
    mp_module, success = await loop.run_in_executor(None, _load_in_thread)
    
    _mp_module = mp_module
    MEDIAPIPE_AVAILABLE = success
    _mp_loading = False
    
    if success:
        print("✅ MediaPipe 背景載入完成！現在可以開始錄影")
    else:
        print("⚠️ MediaPipe 未安裝，手部追蹤功能將不可用")
        print("   安裝指令: pip install mediapipe")
    
    return success


def is_mediapipe_ready() -> bool:
    """檢查 MediaPipe 是否已準備好使用"""
    return MEDIAPIPE_AVAILABLE and _mp_module is not None


def is_mediapipe_loading() -> bool:
    """檢查 MediaPipe 是否正在載入中"""
    return _mp_loading


@dataclass
class MotionFrame:
    """單一動作幀資料
    
    Attributes:
        timestamp: 時間戳（秒，相對於記錄開始）
        emg_data: 8 通道 EMG 訊號（μV）
        hand_landmarks: 21 個手部關鍵點 3D 座標（歸一化 0-1），若未偵測到則為 None
        frame_image: 攝影機影像（BGR 格式），若停用攝影機則為 None
    """
    timestamp: float
    emg_data: np.ndarray  # shape: (8,)
    hand_landmarks: Optional[np.ndarray] = None  # shape: (21, 3)
    frame_image: Optional[np.ndarray] = None


@dataclass
class RecordingSession:
    """記錄會話資料
    
    Attributes:
        frames: 所有記錄的幀
        metadata: 會話元資料
        start_time: 開始時間（Unix timestamp）
        gesture_label: 手勢標籤（如 "fist", "open" 等）
    """
    frames: List[MotionFrame] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    start_time: float = 0.0
    gesture_label: str = ""


class MotionRecorder:
    """EMG + 攝影機同步記錄器
    
    此類負責同步記錄 EMG 訊號、攝影機影像與手部骨架追蹤資料。
    
    使用範例：
        recorder = MotionRecorder(enable_camera=True)
        recorder.start_recording(gesture_label="fist")
        
        # 在 EMG 資料回調中
        recorder.add_emg_sample(emg_channels)
        
        recorder.stop_recording("recordings/fist_001.npz")
    """
    
    # 記憶體管理：最多保留多少幀的完整影像（其餘只保留 landmarks）
    MAX_FULL_IMAGE_FRAMES = 100  # 約 0.5 秒的影像（200Hz EMG）
    
    def __init__(
        self, 
        enable_camera: bool = True,
        camera_id: int = 0,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5
    ):
        """初始化動作記錄器
        
        Args:
            enable_camera: 是否啟用攝影機（False 時只記錄 EMG）
            camera_id: 攝影機 ID（通常 0 是內建攝影機）
            min_detection_confidence: MediaPipe 偵測信心度閾值
            min_tracking_confidence: MediaPipe 追蹤信心度閾值
        """
        self.enable_camera = enable_camera and is_mediapipe_ready()
        self.recording = False
        self.session: Optional[RecordingSession] = None
        
        # 攝影機設置（延遲開啟，直到開始錄影）
        self.camera_id = camera_id
        self.cap: Optional[cv2.VideoCapture] = None
        self.mp_hands = None
        self.hands = None
        self.min_detection_confidence = min_detection_confidence
        self.min_tracking_confidence = min_tracking_confidence
        
        # 快取最新幀以避免重複讀取攝影機
        self._cached_frame: Optional[np.ndarray] = None
        self._cached_landmarks: Optional[np.ndarray] = None
        self._cached_has_hand: bool = False
        self._frame_counter: int = 0
        self._process_every_n_frames: int = 3  # 每 3 幀才做一次 MediaPipe 處理（降低 CPU）
        
        # 攝影機線程（背景讀取，避免阻塞主線程）
        self._camera_thread: Optional[threading.Thread] = None
        self._camera_thread_running = False
        self._camera_lock = threading.Lock()
        
        if not is_mediapipe_ready():
            print("⚠️ MediaPipe 尚未載入完成，攝影機功能已停用")
            self.enable_camera = False
    
    def _init_camera(self) -> bool:
        """開啟攝影機（macOS 使用 AVFoundation 硬體加速）
        
        Returns:
            是否成功開啟
        """
        if self.cap is not None and self.cap.isOpened():
            return True  # 已經開啟
        
        # macOS: 使用 AVFoundation 後端以獲得硬體加速
        import platform
        if platform.system() == 'Darwin':  # macOS
            self.cap = cv2.VideoCapture(self.camera_id, cv2.CAP_AVFOUNDATION)
            print("🍎 使用 AVFoundation (硬體加速)")
        else:
            self.cap = cv2.VideoCapture(self.camera_id)
        
        if not self.cap.isOpened():
            print(f"⚠️ 無法開啟攝影機 {self.camera_id}")
            return False
        
        # 設置更低解析度和幀率以提升效能並降低記憶體使用
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)   # 從 480 降至 320
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)  # 從 360 降至 240
        self.cap.set(cv2.CAP_PROP_FPS, 15)            # 維持 15 FPS
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)      # 減少緩衝區，降低延遲
        
        # macOS 優化：啟用硬體解碼
        if platform.system() == 'Darwin':
            self.cap.set(cv2.CAP_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_ANY)
        
        print(f"✅ 攝影機 {self.camera_id} 已開啟 (320x240 @ 15fps)")
        
        # 啟動攝影機捕捉線程
        self._start_camera_thread()
        
        return True
    
    def _start_camera_thread(self) -> None:
        """啟動攝影機背景線程"""
        if self._camera_thread is not None and self._camera_thread.is_alive():
            return  # 已經在運行
        
        self._camera_thread_running = True
        self._camera_thread = threading.Thread(
            target=self._camera_capture_loop,
            daemon=True,  # 守護線程，主程式結束時自動停止
            name="CameraCapture"
        )
        self._camera_thread.start()
    
    def _stop_camera_thread(self) -> None:
        """停止攝影機背景線程"""
        if self._camera_thread is None:
            return
        
        self._camera_thread_running = False
        if self._camera_thread.is_alive():
            self._camera_thread.join(timeout=2.0)  # 等待最多 2 秒
        self._camera_thread = None
    
    def _close_camera(self) -> None:
        """關閉攝影機，釋放資源"""
        self._stop_camera_thread()  # 先停止線程
        
        if self.cap is not None:
            self.cap.release()
            self.cap = None
            print("✅ 攝影機已關閉")
    
    def _init_mediapipe(self) -> bool:
        """初始化 MediaPipe 手部追蹤
        
        Returns:
            是否成功初始化
        """
        if self.hands is not None:
            return True  # 已經初始化
        
        mp = _lazy_import_mediapipe()
        if mp is None:
            return False
        
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,  # 只追蹤一隻手
            model_complexity=0,  # 使用輕量級模型 (0=輕量, 1=完整)
            min_detection_confidence=self.min_detection_confidence,
            min_tracking_confidence=self.min_tracking_confidence
        )
        print("✅ MediaPipe 手部追蹤已初始化（輕量級模型）")
        return True
    
    def _camera_capture_loop(self) -> None:
        """攝影機捕捉線程（背景運行，避免阻塞主線程）"""
        print("🎬 攝影機線程已啟動")
        
        while self._camera_thread_running:
            if self.cap is None or not self.cap.isOpened():
                time.sleep(0.01)
                continue
            
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            
            # 水平翻轉影像（修正鏡像問題）
            frame = cv2.flip(frame, 1)
            
            self._frame_counter += 1
            
            # 只在特定幀才做 MediaPipe 處理
            should_process = (self._frame_counter % self._process_every_n_frames == 0)
            
            with self._camera_lock:
                # 釋放舊幀（防止記憶體洩漏）
                if self._cached_frame is not None:
                    del self._cached_frame
                
                self._cached_frame = frame.copy()
                
                if should_process and self.hands is not None:
                    try:
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        results = self.hands.process(frame_rgb)
                        
                        # 釋放 RGB 幀（已處理完畢）
                        del frame_rgb
                        
                        if results.multi_hand_landmarks:
                            hand = results.multi_hand_landmarks[0]
                            
                            # 釋放舊 landmarks
                            if self._cached_landmarks is not None:
                                del self._cached_landmarks
                            
                            self._cached_landmarks = np.array([
                                [lm.x, lm.y, lm.z] 
                                for lm in hand.landmark
                            ])
                            self._cached_has_hand = True
                        else:
                            self._cached_landmarks = None
                            self._cached_has_hand = False
                    except Exception as e:
                        print(f"⚠️ MediaPipe 處理錯誤: {e}")
            
            # 釋放原始幀（已複製到快取）
            del frame
            
            # 控制幀率（約 15fps）
            time.sleep(1.0 / 15.0)
        
        print("🎬 攝影機線程已停止")
    
    def __del__(self):
        """解構函數：確保攝影機被正確關閉"""
        self._stop_camera_thread()
        self._close_camera()
    
    def start_recording(self, gesture_label: str = "") -> bool:
        """開始記錄
        
        Args:
            gesture_label: 手勢標籤（如 "fist", "open", "pinch"）
            
        Returns:
            是否成功開始記錄
        """
        if self.recording:
            print("⚠️ 已經在記錄中")
            return False
        
        # 如果啟用攝影機，先開啟攝影機和 MediaPipe
        if self.enable_camera:
            if not self._init_camera():
                print("⚠️ 攝影機開啟失敗，將只記錄 EMG 資料")
                self.enable_camera = False
            elif not self._init_mediapipe():
                print("⚠️ MediaPipe 初始化失敗，將只記錄 EMG 資料")
                self.enable_camera = False
        
        self.recording = True
        self.session = RecordingSession(
            start_time=time.time(),
            gesture_label=gesture_label
        )
        
        # 記錄元資料
        self.session.metadata = {
            'gesture_label': gesture_label,
            'sample_rate': 200,  # EMG 採樣率
            'camera_enabled': self.enable_camera,
            'camera_fps': 30 if self.enable_camera else 0,
            'start_time': time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        
        print(f"✅ 開始記錄: {gesture_label if gesture_label else '未標記'}")
        return True
    
    def add_emg_sample(self, emg_channels: List[float]) -> bool:
        """新增 EMG 樣本（由主程式的資料回調函數呼叫）
        
        此函數現在只從快取讀取，不會阻塞（攝影機在背景線程處理）
        
        Args:
            emg_channels: 8 通道 EMG 資料（μV）
            
        Returns:
            是否成功新增
        """
        if not self.recording or self.session is None:
            return False
        
        # 計算相對時間戳
        timestamp = time.time() - self.session.start_time
        
        # 從快取讀取最新幀和關鍵點（不阻塞）
        frame_image = None
        landmarks = None
        
        if self.enable_camera:
            with self._camera_lock:
                if self._cached_frame is not None:
                    frame_image = self._cached_frame.copy()
                if self._cached_landmarks is not None:
                    landmarks = self._cached_landmarks.copy()
        
        # 建立幀資料
        motion_frame = MotionFrame(
            timestamp=timestamp,
            emg_data=np.array(emg_channels, dtype=np.float32),
            hand_landmarks=landmarks,
            frame_image=frame_image
        )
        
        self.session.frames.append(motion_frame)
        
        # 記憶體管理：定期清理舊幀的影像（保留最新的 MAX_FULL_IMAGE_FRAMES 幀）
        if len(self.session.frames) > self.MAX_FULL_IMAGE_FRAMES:
            # 清理舊幀的影像，只保留 landmarks 和 EMG
            old_frame = self.session.frames[len(self.session.frames) - self.MAX_FULL_IMAGE_FRAMES - 1]
            if old_frame.frame_image is not None:
                del old_frame.frame_image
                old_frame.frame_image = None
        
        return True
    
    def get_current_frame(self) -> tuple[Optional[np.ndarray], bool]:
        """獲取當前攝影機幀（用於預覽視窗）
        
        使用快取的幀，避免重複讀取攝影機和 MediaPipe 處理
        
        Returns:
            (frame, has_hand): 影像幀和是否偵測到手部
        """
        if not self.enable_camera or self._cached_frame is None:
            return None, False
        
        frame = self._cached_frame.copy()
        has_hand = self._cached_has_hand
        
        # 如果有偵測到手部，繪製關鍵點
        if has_hand and self._cached_landmarks is not None:
            # 將歸一化座標轉為像素座標
            h, w = frame.shape[:2]
            landmarks_2d = np.array([
                [int(lm[0] * w), int(lm[1] * h)]
                for lm in self._cached_landmarks
            ])
            frame = self._draw_landmarks_on_frame(frame, landmarks_2d)
        
        return frame, has_hand
    
    def _draw_landmarks_on_frame(
        self, 
        frame: np.ndarray, 
        landmarks_2d: np.ndarray
    ) -> np.ndarray:
        """在影像上繪製手部關鍵點（2D 像素座標）
        
        Args:
            frame: 原始影像（BGR）
            landmarks_2d: 21 個關鍵點的 2D 像素座標 (21, 2)
            
        Returns:
            繪製後的影像
        """
        # 繪製關鍵點
        for point in landmarks_2d:
            cv2.circle(frame, tuple(point), 3, (0, 255, 0), -1)
        
        # 繪製連線（手指骨架）
        connections = [
            # 大拇指
            (0, 1), (1, 2), (2, 3), (3, 4),
            # 食指
            (0, 5), (5, 6), (6, 7), (7, 8),
            # 中指
            (0, 9), (9, 10), (10, 11), (11, 12),
            # 無名指
            (0, 13), (13, 14), (14, 15), (15, 16),
            # 小指
            (0, 17), (17, 18), (18, 19), (19, 20),
            # 手掌
            (5, 9), (9, 13), (13, 17)
        ]
        
        for start_idx, end_idx in connections:
            if start_idx < len(landmarks_2d) and end_idx < len(landmarks_2d):
                start_point = tuple(landmarks_2d[start_idx])
                end_point = tuple(landmarks_2d[end_idx])
                cv2.line(frame, start_point, end_point, (255, 0, 0), 2)
        
        return frame
    
    def stop_recording(self, save_path: str) -> bool:
        """停止記錄並儲存資料
        
        Args:
            save_path: 儲存路徑（.npz 格式）
            
        Returns:
            是否成功儲存
        """
        if not self.recording or self.session is None:
            print("⚠️ 沒有進行中的記錄")
            return False
        
        self.recording = False
        
        if len(self.session.frames) == 0:
            print("⚠️ 沒有記錄到任何資料")
            return False
        
        # 更新元資料
        self.session.metadata['duration'] = time.time() - self.session.start_time
        self.session.metadata['num_frames'] = len(self.session.frames)
        
        # 儲存資訊（在重置 session 前）
        duration = self.session.metadata['duration']
        num_frames = self.session.metadata['num_frames']
        
        # 儲存資料
        success = self._save_data(save_path)
        
        # 儲存影片（如果有攝影機資料）
        if self.enable_camera and self.session.frames[0].frame_image is not None:
            video_path = save_path.replace('.npz', '.mp4')
            self._save_video(video_path)
        
        # 關閉攝影機，釋放資源
        self._close_camera()
        
        # 清理快取（防止記憶體洩漏）
        self._cached_frame = None
        self._cached_landmarks = None
        self._cached_has_hand = False
        
        # 強制垃圾回收
        import gc
        gc.collect()
        
        # 重置會話
        self.session = None
        
        if success:
            print(f"✅ 資料已儲存: {save_path}")
            print(f"   時長: {duration:.2f} 秒")
            print(f"   幀數: {num_frames}")
        
        return success
    
    def _save_data(self, path: str) -> bool:
        """儲存資料為 .npz 格式"""
        try:
            # 建立目錄
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            
            # 準備資料
            timestamps = np.array([f.timestamp for f in self.session.frames])
            emg_data = np.array([f.emg_data for f in self.session.frames])
            
            # 手部關鍵點（可能有 None）
            landmarks_list = []
            for f in self.session.frames:
                if f.hand_landmarks is not None:
                    landmarks_list.append(f.hand_landmarks)
                else:
                    landmarks_list.append(np.zeros((21, 3)))  # 填充零
            
            landmarks = np.array(landmarks_list)
            
            # 標記哪些幀有有效的手部偵測
            landmarks_valid = np.array([
                f.hand_landmarks is not None 
                for f in self.session.frames
            ])
            
            # 儲存
            np.savez(
                path,
                timestamps=timestamps,
                emg_data=emg_data,
                landmarks=landmarks,
                landmarks_valid=landmarks_valid,
                metadata=self.session.metadata
            )
            
            return True
            
        except Exception as e:
            print(f"❌ 儲存資料失敗: {e}")
            return False
    
    def _save_video(self, path: str) -> bool:
        """儲存影片"""
        try:
            if not self.session.frames or self.session.frames[0].frame_image is None:
                return False
            
            # 建立目錄
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            
            # 取得影像尺寸
            height, width = self.session.frames[0].frame_image.shape[:2]
            
            # 建立影片寫入器
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            fps = self.session.metadata.get('camera_fps', 30)
            out = cv2.VideoWriter(path, fourcc, fps, (width, height))
            
            # 寫入每一幀
            for frame in self.session.frames:
                if frame.frame_image is not None:
                    # 可選：在影像上繪製手部關鍵點
                    img = frame.frame_image.copy()
                    if frame.hand_landmarks is not None:
                        img = self._draw_landmarks(img, frame.hand_landmarks)
                    out.write(img)
            
            out.release()
            print(f"✅ 影片已儲存: {path}")
            return True
            
        except Exception as e:
            print(f"❌ 儲存影片失敗: {e}")
            return False
    
    def _draw_landmarks(
        self, 
        image: np.ndarray, 
        landmarks: np.ndarray
    ) -> np.ndarray:
        """在影像上繪製手部關鍵點
        
        Args:
            image: 原始影像（BGR）
            landmarks: 21 個關鍵點座標（歸一化）
            
        Returns:
            繪製後的影像
        """
        height, width = image.shape[:2]
        
        # 繪製關鍵點
        for i, (x, y, z) in enumerate(landmarks):
            cx, cy = int(x * width), int(y * height)
            cv2.circle(image, (cx, cy), 5, (0, 255, 0), -1)
            cv2.putText(
                image, str(i), (cx + 5, cy - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 255, 255), 1
            )
        
        # 繪製連接線（手部骨架）
        if self.mp_hands is not None:
            connections = self.mp_hands.HAND_CONNECTIONS
            for connection in connections:
                start_idx, end_idx = connection
                start = landmarks[start_idx]
                end = landmarks[end_idx]
                
                start_pt = (int(start[0] * width), int(start[1] * height))
                end_pt = (int(end[0] * width), int(end[1] * height))
                
                cv2.line(image, start_pt, end_pt, (0, 255, 0), 2)
        
        return image
    
    def get_preview_frame(self) -> Optional[np.ndarray]:
        """取得當前的攝影機預覽幀（用於 UI 顯示）
        
        Returns:
            當前幀影像（BGR），若攝影機未啟用則返回 None
        """
        if not self.enable_camera or self.cap is None:
            return None
        
        ret, frame = self.cap.read()
        if not ret:
            return None
        
        # 處理手部追蹤
        if self.hands is not None:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(frame_rgb)
            
            if results.multi_hand_landmarks:
                hand = results.multi_hand_landmarks[0]
                landmarks = np.array([
                    [lm.x, lm.y, lm.z] 
                    for lm in hand.landmark
                ])
                frame = self._draw_landmarks(frame, landmarks)
        
        return frame
    
    def release(self) -> None:
        """釋放資源"""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        
        if self.hands is not None:
            try:
                self.hands.close()
            except (ValueError, AttributeError):
                # MediaPipe 可能已經關閉
                pass
            self.hands = None
    
    def __del__(self):
        """解構函數"""
        try:
            self.release()
        except Exception:
            pass  # 忽略解構時的錯誤


def test_motion_recorder():
    """測試動作記錄器（獨立測試）"""
    print("🧪 測試 MotionRecorder...")
    print()
    
    # 檢查 MediaPipe 可用性
    if MEDIAPIPE_AVAILABLE:
        print("✅ MediaPipe 已安裝，將測試完整功能（含攝影機）")
        enable_camera = True
    else:
        print("⚠️  MediaPipe 未安裝，僅測試 EMG 資料記錄")
        print("   注意: Python 3.13 目前不支援 MediaPipe")
        print("   建議使用 Python 3.10 或 3.11 以啟用完整功能")
        enable_camera = False
    
    print()
    
    # 建立記錄器
    recorder = MotionRecorder(enable_camera=enable_camera)
    
    # 開始記錄
    recorder.start_recording("test_gesture")
    
    # 模擬 EMG 資料
    import random
    print("📊 正在記錄模擬 EMG 資料...")
    for i in range(200):  # 1 秒（@ 200 Hz）
        emg_data = [random.uniform(-1000, 1000) for _ in range(8)]
        recorder.add_emg_sample(emg_data)
        time.sleep(0.005)  # 5ms
        
        # 顯示進度
        if (i + 1) % 50 == 0:
            print(f"   已記錄 {i + 1}/200 幀")
    
    print()
    
    # 停止並儲存
    recorder.stop_recording("recordings/test_001.npz")
    
    # 釋放資源
    recorder.release()
    
    print()
    print("✅ 測試完成")
    print()
    
    # 驗證儲存的資料
    print("🔍 驗證儲存的資料...")
    try:
        data = np.load("recordings/test_001.npz", allow_pickle=True)
        print(f"   ✓ 時間戳數量: {len(data['timestamps'])}")
        print(f"   ✓ EMG 資料形狀: {data['emg_data'].shape}")
        print(f"   ✓ 手部關鍵點形狀: {data['landmarks'].shape}")
        print(f"   ✓ 有效關鍵點數: {np.sum(data['landmarks_valid'])}")
        
        metadata = data['metadata'].item()
        print(f"   ✓ 手勢標籤: {metadata['gesture_label']}")
        print(f"   ✓ 記錄時長: {metadata['duration']:.2f} 秒")
        print(f"   ✓ 採樣率: {metadata['sample_rate']} Hz")
        
        print()
        print("✅ 資料驗證成功！")
        
    except Exception as e:
        print(f"   ❌ 驗證失敗: {e}")


if __name__ == "__main__":
    test_motion_recorder()
