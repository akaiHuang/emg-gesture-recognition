"""Qt main window for the EMG monitor application."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore, QtWidgets, QtGui
from qasync import asyncSlot

# macOS 優化設定：降低 CPU 使用率
pg.setConfigOptions(
    useOpenGL=False,  # 關閉 OpenGL（macOS 已棄用，改用原生 Metal）
    antialias=False,   # 關閉抗鋸齒以提升效能
    enableExperimental=False,  # 關閉實驗性功能
    # 其他優化
    useCupy=False,     # 不使用 CUDA
    useNumba=False,    # 不使用 Numba JIT
)

from .. import config
from ..buffers import EmgRingBuffer
from ..data_parser import EmgSample, ImuSample
from ..device_manager import DeviceManager
from ..sim_device import SimulatedDeviceManager
from ..serial_device import SerialDeviceManager
from ..motion_recorder import (
    MotionRecorder,
    is_mediapipe_ready,
    is_mediapipe_loading,
)
from .. import motion_recorder as mr  # 用於呼叫 async 函數


class CameraPreviewWindow(QtWidgets.QWidget):
    """攝影機預覽視窗（獨立視窗）"""
    
    def __init__(self, parent=None):
        super().__init__(None)  # None = 獨立視窗，不附屬於主視窗
        self.setWindowTitle("📹 攝影機預覽")
        # 降低解析度減輕 UI 負擔（配合 320x240 攝影機）
        self.setFixedSize(320, 240)  # 從 480x360 降至 320x240
        
        # 建立 UI
        layout = QtWidgets.QVBoxLayout(self)
        
        # 影像顯示標籤
        self.image_label = QtWidgets.QLabel()
        self.image_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(False)
        self.image_label.setStyleSheet("QLabel { background-color: black; }")
        layout.addWidget(self.image_label)
        
        # 狀態標籤
        self.status_label = QtWidgets.QLabel("正在等待攝影機...")
        self.status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
    
    def update_frame(self, frame: np.ndarray, has_hand: bool = False) -> None:
        """更新顯示的影像幀
        
        Args:
            frame: BGR 格式的影像（OpenCV）
            has_hand: 是否偵測到手部
        """
        if frame is None:
            return
        
        # 轉換為 RGB（Qt 使用 RGB 格式）
        rgb_frame = frame[:, :, ::-1].copy()
        
        # 轉換為 QImage
        height, width, channel = rgb_frame.shape
        bytes_per_line = channel * width
        q_image = QtGui.QImage(
            rgb_frame.data, 
            width, 
            height, 
            bytes_per_line, 
            QtGui.QImage.Format.Format_RGB888
        )
        
        # 直接設定固定大小的 pixmap（不再動態縮放）
        pixmap = QtGui.QPixmap.fromImage(q_image)
        # 使用快速縮放模式以提升效能
        scaled_pixmap = pixmap.scaled(
            320, 240,  # 從 480x360 降至 320x240
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.FastTransformation  # 改用快速模式
        )
        
        self.image_label.setPixmap(scaled_pixmap)
        
        # 更新狀態
        if has_hand:
            self.status_label.setText("✅ 偵測到手部")
            self.status_label.setStyleSheet("QLabel { color: green; font-weight: bold; }")
        else:
            self.status_label.setText("⚠️ 未偵測到手部")
            self.status_label.setStyleSheet("QLabel { color: orange; }")
    
    def closeEvent(self, event):
        """視窗關閉時的處理"""
        self.hide()
        event.ignore()  # 不真正關閉，只是隱藏


class PacketBridge(QtCore.QObject):
    """Bridge raw callbacks to Qt signals."""

    emg_received = QtCore.pyqtSignal(object)
    imu_received = QtCore.pyqtSignal(object)
    status_changed = QtCore.pyqtSignal(str)

    def emit_packet(self, packet: EmgSample | ImuSample) -> None:
        if isinstance(packet, EmgSample):
            self.emg_received.emit(packet)
        else:
            self.imu_received.emit(packet)

    def emit_status(self, message: str) -> None:
        self.status_changed.emit(message)


@dataclass
class DeviceEntry:
    label: str
    address: str


class MainWindow(QtWidgets.QMainWindow):
    """Top-level application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("WL-EMG Monitor")
        self._bridge = PacketBridge()
        self._bridge.emg_received.connect(self._handle_emg_sample)
        self._bridge.imu_received.connect(self._handle_imu_sample)
        self._bridge.status_changed.connect(self._handle_status_update)

        self._real_manager = DeviceManager(
            notification_uuid=config.DEFAULT_NOTIFICATION_UUID,
            on_packet=self._bridge.emit_packet,
            on_status=self._bridge.emit_status,
        )
        self._serial_manager = SerialDeviceManager(
            on_packet=self._bridge.emit_packet,
            on_status=self._bridge.emit_status,
        )
        self._sim_manager = SimulatedDeviceManager(
            on_packet=self._bridge.emit_packet,
            on_status=self._bridge.emit_status,
        )
        self._active_manager: Optional[
            DeviceManager | SerialDeviceManager | SimulatedDeviceManager
        ] = None

        self._device_items: Dict[int, DeviceEntry] = {}
        self._connected = False
        self._buffer = EmgRingBuffer(
            channels=config.EMG_CHANNELS,
            capacity=config.SAMPLE_RATE_HZ * config.BUFFER_SECONDS,
        )
        self._display_offsets = [
            idx * 400.0 for idx in range(config.EMG_CHANNELS)
        ]
        
        # 狀態追蹤
        self._last_packet_time = 0.0
        self._packet_count = 0
        self._signal_strength = 0.0
        self._is_simulation = False
        
        # 通道基線追蹤（用於計算變化量）
        self._channel_baseline = [0.0] * config.EMG_CHANNELS
        self._channel_last_values = [0.0] * config.EMG_CHANNELS
        self._channel_current_state = [0] * config.EMG_CHANNELS  # 當前狀態（0=待機灰, 1=微弱紅, 2=良好黃, 3=強訊綠, 4=最佳藍）
        self._channel_noise_level = [0.0] * config.EMG_CHANNELS  # 每個通道的基線噪音水平
        self._baseline_initialized = False  # 基線是否已初始化
        self._initialization_samples = 500  # 初始化需要的樣本數（約2.5秒）
        self._last_baseline_reset = 0  # 上次基線重置時間
        
        # 個別視圖更新計數器（降低更新頻率以提升效能）
        self._individual_plot_update_counter = 0
        self._individual_plot_update_interval = 25  # 每 25 次才更新個別視圖（1 FPS = 5 FPS / 5）
        
        # 通道輪流更新（不是每次全更新 8 個通道）
        self._channel_update_index = 0
        self._channels_per_update = 2  # 每次只更新 2 個通道
        
        # 攝影機預覽更新控制（降低幀率以提升效能）
        self._camera_frame_counter = 0
        self._camera_frame_skip = 13  # 每 13 個 EMG 樣本更新一次預覽（200Hz / 13 ≈ 15fps）

        # 動作記錄器
        self._motion_recorder: Optional[MotionRecorder] = None
        self._recording = False
        self._recording_start_time = 0.0
        self._mediapipe_ready = False  # MediaPipe 是否已載入完成
        
        # 攝影機預覽視窗
        self._camera_preview: Optional[CameraPreviewWindow] = None

        self._build_ui()
        self._plot_timer = QtCore.QTimer(self)
        self._plot_timer.setInterval(200)  # 5 FPS - 降低 CPU 負載（從 20 FPS 改為 5 FPS）
        self._plot_timer.timeout.connect(self._refresh_plot)
        self._plot_timer.start()

        self._log("Ready.")
        
        # 使用 QTimer 在事件循環啟動後才開始背景載入 MediaPipe
        QtCore.QTimer.singleShot(100, lambda: asyncio.create_task(self._preload_mediapipe()))

    # ------------------------------------------------------------------ UI --
    def _build_ui(self) -> None:
        central = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(central)
        
        # 第一排控制按鈕：序列埠檢測
        usb_layout = QtWidgets.QHBoxLayout()
        
        self._usb_scan_button = QtWidgets.QPushButton("🔍 Search Serial Ports")
        self._usb_scan_button.clicked.connect(self._on_usb_scan_clicked)
        self._usb_scan_button.setStyleSheet("font-weight: bold; background-color: #4CD964; color: white;")
        usb_layout.addWidget(self._usb_scan_button)
        
        # 序列埠列表下拉選單
        self._usb_device_combo = QtWidgets.QComboBox()
        self._usb_device_combo.setMinimumWidth(400)
        self._usb_device_combo.addItem("尚未掃描 - 請點擊 Search Serial Ports")
        usb_layout.addWidget(self._usb_device_combo, stretch=1)
        
        self._usb_info_label = QtWidgets.QLabel("點擊按鈕檢測 USB 序列埠（藍牙接收器）")
        self._usb_info_label.setStyleSheet("color: gray; font-style: italic;")
        usb_layout.addWidget(self._usb_info_label)
        usb_layout.addStretch()
        
        layout.addLayout(usb_layout)
        
        # 第二排控制按鈕：藍牙裝置掃描與連接
        controls_layout = QtWidgets.QHBoxLayout()

        self._scan_button = QtWidgets.QPushButton("Search Bluetooth Devices")
        self._scan_button.clicked.connect(self._on_scan_clicked)
        self._scan_button.hide()  # 暫時隱藏藍牙掃描按鈕
        controls_layout.addWidget(self._scan_button)

        self._device_combo = QtWidgets.QComboBox()
        controls_layout.addWidget(self._device_combo)
        self._device_combo.addItem("Simulation", userData="SIM")
        self._device_items = {0: DeviceEntry("Simulation", "SIM")}

        self._connect_button = QtWidgets.QPushButton("Connect")
        self._connect_button.clicked.connect(self._on_connect_clicked)
        controls_layout.addWidget(self._connect_button)

        self._disconnect_button = QtWidgets.QPushButton("Disconnect")
        self._disconnect_button.clicked.connect(self._on_disconnect_clicked)
        self._disconnect_button.setEnabled(False)
        controls_layout.addWidget(self._disconnect_button)

        layout.addLayout(controls_layout)

        # 狀態指示器區域
        status_group = QtWidgets.QGroupBox("系統狀態")
        status_layout = QtWidgets.QHBoxLayout()
        
        # 1. USB 接收器狀態（新增）
        self._usb_status_label = QtWidgets.QLabel("🔌 USB 接收器")
        self._usb_status_indicator = QtWidgets.QLabel("●")
        self._usb_status_indicator.setStyleSheet("color: gray; font-size: 20px;")
        self._usb_status_text = QtWidgets.QLabel("未檢測")
        self._usb_status_text.setStyleSheet("color: gray;")
        status_layout.addWidget(self._usb_status_label)
        status_layout.addWidget(self._usb_status_indicator)
        status_layout.addWidget(self._usb_status_text)
        status_layout.addSpacing(20)
        
        # 2. 藍牙功能狀態
        self._bt_status_label = QtWidgets.QLabel("� 藍牙功能")
        self._bt_status_indicator = QtWidgets.QLabel("●")
        self._bt_status_indicator.setStyleSheet("color: gray; font-size: 20px;")
        status_layout.addWidget(self._bt_status_label)
        status_layout.addWidget(self._bt_status_indicator)
        status_layout.addSpacing(20)
        
        # 3. 裝置連接狀態
        self._device_status_label = QtWidgets.QLabel("📱 EMG 裝置")
        self._device_status_indicator = QtWidgets.QLabel("●")
        self._device_status_indicator.setStyleSheet("color: gray; font-size: 20px;")
        status_layout.addWidget(self._device_status_label)
        status_layout.addWidget(self._device_status_indicator)
        status_layout.addSpacing(20)
        
        # 4. 訊號接收狀態
        self._signal_status_label = QtWidgets.QLabel("� 訊號接收")
        self._signal_status_indicator = QtWidgets.QLabel("●")
        self._signal_status_indicator.setStyleSheet("color: gray; font-size: 20px;")
        status_layout.addWidget(self._signal_status_label)
        status_layout.addWidget(self._signal_status_indicator)
        status_layout.addSpacing(20)
        
        # 5. 訊號強度
        self._strength_label = QtWidgets.QLabel("💪 訊號強度: --")
        status_layout.addWidget(self._strength_label)
        status_layout.addStretch()
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # 動作記錄控制區
        recording_group = QtWidgets.QGroupBox("🎬 動作記錄")
        recording_layout = QtWidgets.QHBoxLayout()
        
        # 手勢標籤選擇
        recording_layout.addWidget(QtWidgets.QLabel("手勢標籤:"))
        self._gesture_combo = QtWidgets.QComboBox()
        self._gesture_combo.addItems([
            "fist",           # 握拳
            "open",           # 張開
            "pinch",          # 捏取
            "thumbs_up",      # 豎起大拇指
            "peace",          # 比YA
            "pointing",       # 食指指向
            "wave",           # 揮手
            "rest",           # 休息/放鬆
            "custom",         # 自定義
        ])
        self._gesture_combo.setMinimumWidth(120)
        recording_layout.addWidget(self._gesture_combo)
        
        # 自定義標籤輸入
        self._custom_label_input = QtWidgets.QLineEdit()
        self._custom_label_input.setPlaceholderText("自定義標籤...")
        self._custom_label_input.setEnabled(False)
        self._custom_label_input.setMinimumWidth(150)
        recording_layout.addWidget(self._custom_label_input)
        
        # 當選擇 custom 時啟用輸入框
        self._gesture_combo.currentTextChanged.connect(
            lambda text: self._custom_label_input.setEnabled(text == "custom")
        )
        
        recording_layout.addSpacing(20)
        
        # 記錄按鈕
        self._record_button = QtWidgets.QPushButton("● 開始記錄")
        self._record_button.clicked.connect(self._on_record_clicked)
        self._record_button.setEnabled(False)  # 初始時停用，等待 MediaPipe 載入
        self._record_button.setToolTip("正在載入 MediaPipe，請稍候...")
        self._record_button.setStyleSheet("""
            QPushButton {
                background-color: #FF3B30;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #FF2D55;
            }
            QPushButton:disabled {
                background-color: #999;
            }
        """)
        self._record_button.setEnabled(False)  # 未連接時禁用
        recording_layout.addWidget(self._record_button)
        
        # 記錄狀態指示
        self._recording_status_label = QtWidgets.QLabel("就緒")
        self._recording_status_label.setStyleSheet("color: gray; font-style: italic;")
        recording_layout.addWidget(self._recording_status_label)
        
        # 記錄時間顯示
        self._recording_time_label = QtWidgets.QLabel("")
        self._recording_time_label.setStyleSheet("color: #FF3B30; font-weight: bold;")
        recording_layout.addWidget(self._recording_time_label)
        
        recording_layout.addStretch()
        
        # 攝影機預覽按鈕（可選）
        self._camera_preview_button = QtWidgets.QPushButton("📷 攝影機預覽")
        self._camera_preview_button.setCheckable(True)
        self._camera_preview_button.clicked.connect(self._on_camera_preview_clicked)
        self._camera_preview_button.setEnabled(False)
        recording_layout.addWidget(self._camera_preview_button)
        
        recording_group.setLayout(recording_layout)
        layout.addWidget(recording_group)

        # 8 通道訊號監控面板
        channels_group = QtWidgets.QGroupBox("8 通道訊號監控")
        channels_layout = QtWidgets.QHBoxLayout()
        
        self._channel_indicators = []
        self._channel_strength_labels = []
        self._channel_quality_labels = []
        
        colors = ["#FF3B30", "#FF9500", "#FFCC00", "#4CD964", "#5AC8FA", "#007AFF", "#5856D6", "#FF2D55"]
        
        for i in range(config.EMG_CHANNELS):
            # 每個通道的垂直佈局
            ch_layout = QtWidgets.QVBoxLayout()
            
            # 通道標籤
            ch_label = QtWidgets.QLabel(f"CH{i+1}")
            ch_label.setStyleSheet(f"font-weight: bold; color: {colors[i]}; font-size: 12px;")
            ch_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            ch_layout.addWidget(ch_label)
            
            # 訊號強度指示器（圓點）
            indicator = QtWidgets.QLabel("●")
            indicator.setStyleSheet("color: gray; font-size: 24px;")
            indicator.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self._channel_indicators.append(indicator)
            ch_layout.addWidget(indicator)
            
            # 訊號強度數值
            strength_label = QtWidgets.QLabel("--")
            strength_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            strength_label.setStyleSheet("font-size: 10px; color: #888;")
            self._channel_strength_labels.append(strength_label)
            ch_layout.addWidget(strength_label)
            
            # 訊號品質
            quality_label = QtWidgets.QLabel("--")
            quality_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            quality_label.setStyleSheet("font-size: 9px; color: #666;")
            self._channel_quality_labels.append(quality_label)
            ch_layout.addWidget(quality_label)
            
            channels_layout.addLayout(ch_layout)
        
        channels_group.setLayout(channels_layout)
        layout.addWidget(channels_group)

        self._status_label = QtWidgets.QLabel("Status: Disconnected")
        layout.addWidget(self._status_label)

        # 全頻道合併視圖（原有的示波器）
        combined_label = QtWidgets.QLabel("📊 全頻道合併視圖")
        combined_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #4CD964;")
        layout.addWidget(combined_label)
        
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground("k")
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self._plot_widget.setLabel("left", "EMG (uV)")
        self._plot_widget.setLabel("bottom", "Time (s)")
        self._plot_widget.setLimits(xMin=-config.BUFFER_SECONDS, xMax=0)
        self._plot_widget.setMinimumHeight(400)  # 確保全頻道視圖有足夠的高度
        layout.addWidget(self._plot_widget, stretch=2)  # 給予更多的伸展空間

        colors = [
            "#FF3B30",
            "#FF9500",
            "#FFCC00",
            "#4CD964",
            "#5AC8FA",
            "#007AFF",
            "#5856D6",
            "#FF2D55",
        ]
        self._curves = [
            self._plot_widget.plot(
                pen=pg.mkPen(color=colors[idx % len(colors)], width=1.5),
                skipFiniteCheck=True  # 跳過有限性檢查（提升效能）
            )
            for idx in range(config.EMG_CHANNELS)
        ]
        
        # 8 個獨立通道視圖
        individual_label = QtWidgets.QLabel("📈 個別通道視圖")
        individual_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #5AC8FA;")
        layout.addWidget(individual_label)
        
        # 建立 2x4 網格佈局來放置 8 個小示波器
        individual_plots_layout = QtWidgets.QGridLayout()
        individual_plots_layout.setSpacing(5)
        
        self._individual_plot_widgets = []
        self._individual_curves = []
        
        for idx in range(config.EMG_CHANNELS):
            # 建立小示波器
            plot_widget = pg.PlotWidget()
            plot_widget.setBackground("#1a1a1a")
            plot_widget.showGrid(x=True, y=True, alpha=0.2)
            plot_widget.setLabel("left", "μV", **{"font-size": "8pt"})
            plot_widget.setLabel("bottom", "Time (s)", **{"font-size": "8pt"})
            plot_widget.setLimits(xMin=-config.BUFFER_SECONDS, xMax=0)
            plot_widget.setTitle(f"CH{idx+1}", color=colors[idx], size="10pt")
            plot_widget.setMinimumHeight(120)  # 最小高度
            plot_widget.setMaximumHeight(180)  # 最大高度
            
            # 效能優化：關閉個別視圖的一些功能
            plot_widget.setClipToView(True)  # 只繪製可見範圍
            plot_widget.setDownsampling(mode='peak')  # 使用降採樣
            
            # 建立曲線（效能優化）
            curve = plot_widget.plot(
                pen=pg.mkPen(color=colors[idx], width=2),
                antialias=False,  # 關閉抗鋸齒以提升效能
                skipFiniteCheck=True,  # 跳過有限性檢查
                connect='finite'  # 忽略無限值
            )
            
            self._individual_plot_widgets.append(plot_widget)
            self._individual_curves.append(curve)
            
            # 將示波器加入網格 (2 行 x 4 列)
            row = idx // 4
            col = idx % 4
            individual_plots_layout.addWidget(plot_widget, row, col)
        
        layout.addLayout(individual_plots_layout)

        self._log_view = QtWidgets.QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumHeight(120)
        layout.addWidget(self._log_view)

        central.setLayout(layout)
        self.setCentralWidget(central)
        self.resize(1200, 1200)

    # -------------------------------------------------------------- Helpers --
    def _current_device(self) -> DeviceEntry:
        idx = self._device_combo.currentIndex()
        entry = self._device_items.get(idx)
        if entry is None:
            raise ValueError("No device selected")
        return entry

    def _set_controls_enabled(self, scanning: bool = False) -> None:
        self._scan_button.setEnabled(not self._connected and not scanning)
        self._connect_button.setEnabled(not self._connected and not scanning)
        self._disconnect_button.setEnabled(self._connected)
        self._device_combo.setEnabled(not self._connected and not scanning)
        self._usb_scan_button.setEnabled(not scanning)
        
        # 記錄按鈕只在：1) 已連接 2) 未記錄中 3) MediaPipe 已載入完成時啟用
        can_record = (
            self._connected 
            and not self._recording 
            and self._mediapipe_ready
        )
        self._record_button.setEnabled(can_record)
        
        # 更新按鈕提示
        if not self._mediapipe_ready:
            if is_mediapipe_loading():
                self._record_button.setToolTip("正在載入 MediaPipe，請稍候...")
            else:
                self._record_button.setToolTip("MediaPipe 載入失敗，無法使用錄影功能")
        elif not self._connected:
            self._record_button.setToolTip("請先連接 EMG 裝置")
        elif self._recording:
            self._record_button.setToolTip("正在記錄中...")
        else:
            self._record_button.setToolTip("開始記錄 EMG 訊號和手部動作")
        
        # 攝影機預覽只在已初始化記錄器時啟用
        self._camera_preview_button.setEnabled(self._motion_recorder is not None)

    def _log(self, message: str) -> None:
        self._log_view.appendPlainText(message)
    
    # -------------------------------------------------- MediaPipe Preloading --
    async def _preload_mediapipe(self) -> None:
        """在背景載入 MediaPipe（不阻塞 UI）"""
        self._log("🔄 開始在背景載入 MediaPipe（這可能需要 10-15 秒）...")
        
        success = await mr._async_import_mediapipe()
        
        if success:
            self._mediapipe_ready = True
            self._log("✅ MediaPipe 載入完成！現在可以開始錄影")
            
            # 啟用記錄按鈕（如果已連接裝置）
            if self._active_manager is not None:
                self._record_button.setEnabled(True)
                self._record_button.setToolTip("開始記錄 EMG 訊號和手部動作")
        else:
            self._log("⚠️ MediaPipe 載入失敗，錄影功能將不可用")
            self._record_button.setToolTip("MediaPipe 未安裝，無法使用錄影功能")

    # ------------------------------------------------------------ Callbacks --
    def _handle_emg_sample(self, sample: EmgSample) -> None:
        try:
            self._buffer.append(sample.channels_uv)
            
            # 同步 EMG 資料到記錄器
            if self._recording and self._motion_recorder is not None:
                self._motion_recorder.add_emg_sample(sample.channels_uv)
                
                # 更新記錄時間顯示
                import time
                elapsed = time.time() - self._recording_start_time
                self._recording_time_label.setText(f"{elapsed:.1f}s")
                
                # 更新攝影機預覽視窗（限制幀率為 15fps）
                self._camera_frame_counter += 1
                if (self._camera_frame_counter >= self._camera_frame_skip
                    and self._camera_preview is not None 
                    and self._camera_preview.isVisible() 
                    and self._motion_recorder.enable_camera):
                    
                    self._camera_frame_counter = 0  # 重置計數器
                    frame, has_hand = self._motion_recorder.get_current_frame()
                    if frame is not None:
                        self._camera_preview.update_frame(frame, has_hand)
            
            # 更新訊號接收狀態
            import time
            self._last_packet_time = time.time()
            self._packet_count += 1
            
            # 初始化階段：只建立基線，不顯示訊號品質
            if not self._baseline_initialized:
                if self._packet_count <= self._initialization_samples:
                    # 快速建立基線並累積活動度（用於計算噪音水平）
                    for i, ch_value in enumerate(sample.channels_uv):
                        alpha = 0.1  # 初始化時使用較快的更新速度
                        self._channel_baseline[i] = alpha * ch_value + (1 - alpha) * self._channel_baseline[i]
                        
                        # 計算當前活動度並累積（用於計算平均噪音水平）
                        if self._packet_count > 50:  # 前50個封包讓基線穩定
                            deviation = abs(ch_value - self._channel_baseline[i])
                            change_rate = abs(ch_value - self._channel_last_values[i])
                            activity = (deviation * 0.7 + change_rate * 0.3)
                            # 累積平均噪音水平
                            self._channel_noise_level[i] += activity
                        
                        self._channel_last_values[i] = ch_value
                    
                    # 顯示初始化進度（降低頻率）
                    if self._packet_count % 100 == 0:
                        progress = (self._packet_count / self._initialization_samples) * 100
                        print(f"基線初始化中... {progress:.0f}%")
                    
                    # 所有通道顯示為灰色「校準中」
                    for i in range(8):
                        if i < len(self._channel_indicators):
                            self._channel_indicators[i].setStyleSheet("color: gray; font-size: 24px;")
                            self._channel_quality_labels[i].setText("校準中")
                            self._channel_quality_labels[i].setStyleSheet("font-size: 9px; color: #888;")
                            self._channel_strength_labels[i].setText("--")
                    
                    return  # 初始化期間不進行訊號品質判斷
                else:
                    # 初始化完成：計算每個通道的平均噪音水平
                    self._baseline_initialized = True
                    for i in range(config.EMG_CHANNELS):
                        # 計算平均噪音（除以有效樣本數）
                        self._channel_noise_level[i] = self._channel_noise_level[i] / (self._initialization_samples - 50)
                    
                    print("基線初始化完成！")
                    print(f"各通道基線: {[f'{b:.0f}' for b in self._channel_baseline]}")
                    print(f"各通道噪音水平: {[f'{n:.0f}' for n in self._channel_noise_level]}")
                    self._last_baseline_reset = self._packet_count
            
            # 定期重新校準基線（每 30 秒，當所有通道都在待機狀態時）
            if self._packet_count - self._last_baseline_reset > 6000:  # 30秒
                all_idle = all(state == 0 for state in self._channel_current_state)
                if all_idle:
                    print("\n⟳ 基線自動重新校準...")
                    self._baseline_initialized = False
                    self._packet_count = 0
                    return
            
            # 正常運作：計算每個通道的訊號活動度（變化量）
            channel_activity = []
            for i, ch_value in enumerate(sample.channels_uv):
                # 計算當前偏離值
                deviation = abs(ch_value - self._channel_baseline[i])
                
                # 改進基線更新策略：使用自適應速率
                if deviation < self._channel_noise_level[i] * 2:
                    # 訊號接近基線，快速更新
                    alpha = 0.02
                elif deviation < self._channel_noise_level[i] * 5:
                    # 中等訊號，慢速更新
                    alpha = 0.002
                else:
                    # 強訊號，極慢更新（但不完全停止）
                    alpha = 0.0001
                
                self._channel_baseline[i] = alpha * ch_value + (1 - alpha) * self._channel_baseline[i]
                
                # 活動度只看偏離值
                activity = deviation
                channel_activity.append(activity)
                
                # 更新上次數值
                self._channel_last_values[i] = ch_value
            
            # 批次更新通道指示器（每 5 個封包更新一次，減少 UI 刷新）
            if self._packet_count % 5 == 0:
                for i, activity in enumerate(channel_activity):
                    self._update_channel_indicator(i, activity)
            
            # 即時監測：每 50 個封包輸出一次（約 250ms 間隔，進一步降低負載）
            # 如果不需要終端機監測，可以註解掉以下整個 if 區塊
            if self._packet_count % 50 == 0:
                # 顯示每個通道的活動度和狀態
                status_map = {0: "待機", 1: "微弱", 2: "良好", 3: "強訊", 4: "最佳"}
                ch_info = []
                active_channels = []  # 記錄活躍的通道
                
                for i in range(len(channel_activity)):
                    state_text = status_map.get(self._channel_current_state[i], "?")
                    # 標記活躍的通道（活動度 > 閾值）
                    threshold = self._channel_noise_level[i] * 2.5
                    if channel_activity[i] > threshold:
                        ch_info.append(f"CH{i+1}:【{channel_activity[i]:.0f}】{state_text}")
                        active_channels.append(i+1)
                    else:
                        ch_info.append(f"CH{i+1}:{channel_activity[i]:.0f}")
                
                # 顯示活躍通道數（用於診斷串擾）
                active_count = len(active_channels)
                if active_count > 1:
                    isolation_warning = f" ⚠️ {active_count}個通道活躍:{active_channels}"
                else:
                    isolation_warning = ""
                
                # 清除舊行並顯示新狀態（使用 \r 回到行首）
                print(f"\r封包#{self._packet_count:5d} | " + " | ".join(ch_info) + isolation_warning, end="", flush=True)
            
            # 計算整體訊號強度
            self._signal_strength = np.mean(channel_activity)
            
            # 更新訊號接收指示器為綠色
            self._signal_status_indicator.setStyleSheet("color: #4CD964; font-size: 20px;")
            
        except ValueError as exc:
            self._log(f"EMG buffer error: {exc}")
    
    def _update_channel_indicator(self, channel_idx: int, strength: float) -> None:
        """更新單個通道的訊號指示器（帶遲滯機制避免跳動）"""
        if channel_idx >= len(self._channel_indicators):
            return
        
        indicator = self._channel_indicators[channel_idx]
        strength_label = self._channel_strength_labels[channel_idx]
        quality_label = self._channel_quality_labels[channel_idx]
        
        # 更新強度數值（顯示活動度）
        strength_label.setText(f"{strength:.0f}")
        
        # 取得當前狀態
        current_state = self._channel_current_state[channel_idx]
        
        # 根據該通道的噪音水平動態設定閾值（倍率法）
        # 新的 5 級系統：
        # 0: 待機（灰色）- 低於 2 倍噪音
        # 1: 微弱（紅色）- 2-4 倍噪音
        # 2: 良好（黃色）- 4-7 倍噪音
        # 3: 強訊（綠色）- 7-12 倍噪音
        # 4: 最佳（淡藍色）- 12 倍以上噪音
        noise_baseline = max(self._channel_noise_level[channel_idx], 100)  # 至少100 μV
        
        # 使用遲滯閾值：上升閾值較高，下降閾值較低（避免反覆跳動）
        # 定義閾值：[下降閾值, 上升閾值]
        thresholds = {
            0: (0, noise_baseline * 2.0),           # 待機 -> 微弱：需要 > 2倍噪音
            1: (noise_baseline * 1.5, noise_baseline * 4.0),  # 微弱 <-> 良好
            2: (noise_baseline * 3.5, noise_baseline * 7.0),  # 良好 <-> 強訊
            3: (noise_baseline * 6.5, noise_baseline * 12.0), # 強訊 <-> 最佳
            4: (noise_baseline * 11.0, 999999)      # 最佳
        }
        
        # 決定新狀態（允許跨級下降）
        new_state = current_state
        
        # 先判斷下降（可以跨級）
        if strength < thresholds[0][1]:
            # 低於微弱閾值，回到待機
            new_state = 0
        elif strength < thresholds[1][1]:
            # 低於良好閾值，但高於微弱閾值
            if current_state >= 2:
                new_state = 1  # 從良好/強訊/最佳降到微弱
        elif strength < thresholds[2][1]:
            # 低於強訊閾值
            if current_state >= 3:
                new_state = 2  # 從強訊/最佳降到良好
        elif strength < thresholds[3][1]:
            # 低於最佳閾值
            if current_state >= 4:
                new_state = 3  # 從最佳降到強訊
        
        # 再判斷上升（需要遲滯）
        if current_state == 0 and strength >= thresholds[0][1]:
            new_state = 1
        elif current_state == 1 and strength >= thresholds[1][1]:
            new_state = 2
        elif current_state == 2 and strength >= thresholds[2][1]:
            new_state = 3
        elif current_state == 3 and strength >= thresholds[3][1]:
            new_state = 4
        
        # 更新狀態
        self._channel_current_state[channel_idx] = new_state
        
        # 根據新狀態設定顯示
        if new_state == 0:
            # 待機：灰色（訊號最差）
            indicator.setStyleSheet("color: gray; font-size: 24px;")
            quality_label.setText("待機")
            quality_label.setStyleSheet("font-size: 9px; color: #888;")
        elif new_state == 1:
            # 微弱：紅色（沒訊號微弱）
            indicator.setStyleSheet("color: #FF3B30; font-size: 24px;")
            quality_label.setText("微弱")
            quality_label.setStyleSheet("font-size: 9px; color: #FF3B30;")
        elif new_state == 2:
            # 良好：黃色
            indicator.setStyleSheet("color: #FFCC00; font-size: 24px;")
            quality_label.setText("良好")
            quality_label.setStyleSheet("font-size: 9px; color: #FFCC00; font-weight: bold;")
        elif new_state == 3:
            # 強訊：綠色
            indicator.setStyleSheet("color: #4CD964; font-size: 24px;")
            quality_label.setText("強訊")
            quality_label.setStyleSheet("font-size: 9px; color: #4CD964; font-weight: bold;")
        else:
            # 最佳：淡藍色（訊號最好）
            indicator.setStyleSheet("color: #5AC8FA; font-size: 24px;")
            quality_label.setText("最佳")
            quality_label.setStyleSheet("font-size: 9px; color: #5AC8FA; font-weight: bold;")

    def _handle_imu_sample(self, sample: ImuSample) -> None:
        gyro = ", ".join(f"{axis:.2f}" for axis in sample.gyro_rads)
        accel = ", ".join(f"{axis:.2f}" for axis in sample.accel_mss)
        self._status_label.setText(
            f"Status: Connected | Gyro {gyro} rad/s | Accel {accel} m/s^2"
        )

    def _handle_status_update(self, message: str) -> None:
        self._log(message)
        prefix = "Status: Connected | " if self._connected else "Status: "
        self._status_label.setText(f"{prefix}{message}")

    def _refresh_plot(self) -> None:
        import time
        
        # 只在連接時更新狀態（減少不必要的操作）
        if not self._connected:
            return
        
        # 更新狀態指示器
        current_time = time.time()
        
        # 檢查訊號是否還在接收（超過1秒沒收到就顯示紅色）
        if (current_time - self._last_packet_time) > 1.0:
            self._signal_status_indicator.setStyleSheet("color: #FF3B30; font-size: 20px;")
            self._strength_label.setText("💪 訊號強度: 無訊號")
        else:
            # 更新訊號強度顯示（簡化）
            if self._signal_strength > 100:
                strength_text = "強🟢"
            elif self._signal_strength > 30:
                strength_text = "中🟡"
            else:
                strength_text = "弱🟠"
            self._strength_label.setText(f"💪 {self._signal_strength:.0f}μV {strength_text}")
        
        # 繪圖（優化：減少數據處理）
        data = self._buffer.snapshot()
        if data.size == 0:
            return
        
        points = data.shape[1]
        duration = points / config.SAMPLE_RATE_HZ
        x = np.linspace(-duration, 0, points)
        
        # 始終更新全頻道合併視圖（主視圖，保持流暢）
        for idx, curve in enumerate(self._curves):
            channel_data = data[idx] + self._display_offsets[idx]
            curve.setData(x, channel_data, skipFiniteCheck=True)  # 跳過有限性檢查以提升效能
        
        # 降低個別通道視圖的更新頻率（輪流更新，不是每次全更新）
        # 錄影時進一步降低更新頻率以減少 CPU 負擔
        is_recording = self._motion_recorder and self._motion_recorder.recording
        update_interval = self._individual_plot_update_interval * 2 if is_recording else self._individual_plot_update_interval
        
        self._individual_plot_update_counter += 1
        if self._individual_plot_update_counter >= update_interval:
            self._individual_plot_update_counter = 0
            # 輪流更新 2 個通道（而不是 8 個全部）
            for i in range(self._channels_per_update):
                ch_idx = (self._channel_update_index + i) % 8
                if ch_idx < len(self._individual_curves):
                    channel_data = data[ch_idx]  # 不需要偏移量，每個通道獨立顯示
                    self._individual_curves[ch_idx].setData(
                        x, channel_data,
                        skipFiniteCheck=True  # 跳過檢查
                    )
            # 下次從下兩個通道開始
            self._channel_update_index = (self._channel_update_index + self._channels_per_update) % 8

        # ---------------------------------------------------------- UI actions --
    @asyncSlot()
    async def _on_usb_scan_clicked(self) -> None:
        """掃描序列埠 (Serial Ports) - 尋找藍牙接收器"""
        self._set_controls_enabled(scanning=True)
        self._log("🔍 掃描序列埠...")
        self._usb_info_label.setText("掃描中...")
        self._usb_info_label.setStyleSheet("color: #FFCC00; font-style: italic;")
        
        # USB 狀態設為檢測中（黃色）
        self._usb_status_indicator.setStyleSheet("color: #FFCC00; font-size: 20px;")
        self._usb_status_text.setText("掃描中...")
        self._usb_status_text.setStyleSheet("color: #FFCC00;")
        
        # 清空列表
        self._usb_device_combo.clear()
        
        try:
            # 使用 SerialDeviceManager 列出序列埠
            usb_serial_ports = SerialDeviceManager.list_ports()
            
            if usb_serial_ports:
                # 找到 USB 序列埠
                self._usb_status_indicator.setStyleSheet("color: #4CD964; font-size: 20px;")
                self._usb_status_text.setText(f"找到 {len(usb_serial_ports)} 個")
                self._usb_status_text.setStyleSheet("color: #4CD964; font-weight: bold;")
                
                info = f"✓ 掃描完成：共找到 {len(usb_serial_ports)} 個 USB 序列埠\n"
                info += "\n提示：選擇序列埠後，點擊 Connect 連接到藍牙接收器"
                self._log(info)
                
                self._usb_info_label.setText(f"✓ 找到 {len(usb_serial_ports)} 個 USB 序列埠")
                self._usb_info_label.setStyleSheet("color: #4CD964; font-weight: bold;")
                
                # 將序列埠加入到設備下拉選單
                self._device_combo.clear()
                self._device_combo.addItem("Simulation", userData="SIM")
                self._device_items = {0: DeviceEntry("Simulation", "SIM")}
                
                idx = 1
                for port in usb_serial_ports:
                    # 標記可能是藍牙接收器的埠
                    if 'usbserial' in port or 'usbmodem' in port:
                        label = f"📡 {port} (USB Serial)"
                    else:
                        label = f"{port} (USB Serial)"
                    
                    self._device_combo.addItem(label, userData=port)
                    self._device_items[idx] = DeviceEntry(label, port)
                    self._usb_device_combo.addItem(label)
                    idx += 1
                
                # 記錄詳細列表
                self._log("\n掃描到的 USB 序列埠：")
                for i, port in enumerate(usb_serial_ports, 1):
                    self._log(f"  {i}. {port}")
                
            else:
                # 沒找到 USB 序列埠
                self._usb_status_indicator.setStyleSheet("color: #FFCC00; font-size: 20px;")
                self._usb_status_text.setText("無序列埠")
                self._usb_status_text.setStyleSheet("color: #FFCC00; font-weight: bold;")
                
                self._usb_device_combo.addItem("未找到 USB 序列埠（請確認藍牙接收器已插入）")
                self._usb_info_label.setText("未找到 USB 序列埠")
                self._usb_info_label.setStyleSheet("color: #FFCC00; font-style: italic;")
                self._log("未找到 USB 序列埠")
                    
        except Exception as exc:
            self._log(f"序列埠掃描失敗: {exc}")
            self._usb_status_indicator.setStyleSheet("color: #FF3B30; font-size: 20px;")
            self._usb_status_text.setText("掃描失敗")
            self._usb_status_text.setStyleSheet("color: #FF3B30;")
            self._usb_device_combo.addItem("掃描失敗")
            self._usb_info_label.setText("✗ 掃描失敗")
            self._usb_info_label.setStyleSheet("color: #FF3B30; font-style: italic;")
        finally:
            self._set_controls_enabled(scanning=False)

    @asyncSlot()
    async def _on_scan_clicked(self) -> None:
        self._set_controls_enabled(scanning=True)
        self._log("Starting Bluetooth scan...")
        
        # 嘗試掃描時，藍牙接收器狀態設為黃色（檢測中）
        self._bt_status_indicator.setStyleSheet("color: #FFCC00; font-size: 20px;")
        
        self._device_combo.clear()
        self._device_combo.addItem("Simulation", userData="SIM")
        self._device_items = {0: DeviceEntry("Simulation", "SIM")}
        try:
            devices = await self._real_manager.scan(
                timeout=config.DEFAULT_SCAN_TIMEOUT
            )
            # 掃描成功，藍牙接收器設為綠色
            self._bt_status_indicator.setStyleSheet("color: #4CD964; font-size: 20px;")
            
            # 檢查是否有 WL 裝置（表示 USB 接收器已連接）
            has_wl_device = any("WL" in (dev.name or "").upper() or 
                               "EEG" in (dev.name or "").upper() 
                               for dev in devices)
            
            if has_wl_device:
                self._usb_status_indicator.setStyleSheet("color: #4CD964; font-size: 20px;")
                self._usb_status_text.setText("已偵測到 WL 裝置")
                self._usb_status_text.setStyleSheet("color: #4CD964; font-weight: bold;")
            else:
                self._usb_status_indicator.setStyleSheet("color: #FFCC00; font-size: 20px;")
                self._usb_status_text.setText("未找到 WL 裝置")
                self._usb_status_text.setStyleSheet("color: #FFCC00;")
            
            # 按 RSSI 排序（訊號強度由強到弱）
            devices_sorted = sorted(devices, key=lambda d: d.rssi or -999, reverse=True)
            
            for dev in devices_sorted:
                # 顯示訊號強度
                rssi_text = f"[{dev.rssi}dBm]" if dev.rssi else "[?]"
                
                # 標記可能的 EMG 相關裝置
                name = dev.name or "(unknown)"
                if any(keyword in name.upper() for keyword in ["EMG", "WL", "SENSOR", "MUSCLE"]):
                    name = f"⭐ {name}"
                
                label = f"{name} {rssi_text} ({dev.address})"
                index = self._device_combo.count()
                self._device_combo.addItem(label, userData=dev.address)
                self._device_items[index] = DeviceEntry(label, dev.address)
            
            self._log(f"Found {len(devices)} device(s). 提示：拔掉 USB 再掃描一次，比較哪個裝置消失了")
        except Exception as exc:
            self._log(f"Scan failed: {exc}")
            # 掃描失敗，藍牙接收器設為紅色
            self._bt_status_indicator.setStyleSheet("color: #FF3B30; font-size: 20px;")
            self._usb_status_indicator.setStyleSheet("color: #FF3B30; font-size: 20px;")
            self._usb_status_text.setText("掃描失敗")
            self._usb_status_text.setStyleSheet("color: #FF3B30;")
        finally:
            self._set_controls_enabled(scanning=False)

    @asyncSlot()
    async def _on_connect_clicked(self) -> None:
        entry = self._current_device()
        if entry.address == "SIM":
            manager = self._sim_manager
            self._is_simulation = True
            # 模擬模式：藍牙為灰色（不使用），裝置為藍色（模擬）
            self._bt_status_indicator.setStyleSheet("color: gray; font-size: 20px;")
            self._device_status_indicator.setStyleSheet("color: #007AFF; font-size: 20px;")
        elif entry.address.startswith('/dev/'):
            # 序列埠模式：透過 USB 藍牙接收器連接
            manager = self._serial_manager
            self._is_simulation = False
            # USB 接收器為綠色（已連接），藍牙為黃色（嘗試連接）
            self._usb_status_indicator.setStyleSheet("color: #4CD964; font-size: 20px;")
            self._usb_status_text.setText("已連接")
            self._usb_status_text.setStyleSheet("color: #4CD964; font-weight: bold;")
            self._bt_status_indicator.setStyleSheet("color: #FFCC00; font-size: 20px;")
            self._device_status_indicator.setStyleSheet("color: #FFCC00; font-size: 20px;")
        else:
            # 藍牙模式（原本的方式）
            manager = self._real_manager
            self._is_simulation = False
            # 真實模式：裝置連接中（黃色）
            self._device_status_indicator.setStyleSheet("color: #FFCC00; font-size: 20px;")
            
        await self._disconnect_active()
        self._active_manager = manager
        try:
            await manager.connect(entry.address)
        except Exception as exc:
            self._log(f"Connection failed: {exc}")
            self._active_manager = None
            # 連接失敗：裝置為紅色
            self._device_status_indicator.setStyleSheet("color: #FF3B30; font-size: 20px;")
            if entry.address.startswith('/dev/'):
                self._usb_status_indicator.setStyleSheet("color: #FF3B30; font-size: 20px;")
                self._usb_status_text.setText("連接失敗")
                self._usb_status_text.setStyleSheet("color: #FF3B30;")
            return
        self._connected = True
        self._buffer.clear()
        self._packet_count = 0
        import time
        self._last_packet_time = time.time()
        self._set_controls_enabled()
        
        # 連接成功：裝置為綠色
        self._device_status_indicator.setStyleSheet("color: #4CD964; font-size: 20px;")
        if entry.address.startswith('/dev/'):
            self._bt_status_indicator.setStyleSheet("color: #4CD964; font-size: 20px;")
        self._log(f"Connected to {entry.label}")

    @asyncSlot()
    async def _on_disconnect_clicked(self) -> None:
        await self._disconnect_active()

    async def _disconnect_active(self) -> None:
        if not self._active_manager:
            return
        
        # 如果正在記錄，先停止
        if self._recording:
            self._stop_recording()
        
        try:
            await self._active_manager.disconnect()
        except Exception as exc:
            self._log(f"Error while disconnecting: {exc}")
        self._active_manager = None
        self._connected = False
        self._packet_count = 0
        self._signal_strength = 0.0
        self._set_controls_enabled()
        self._status_label.setText("Status: Disconnected")
        
        # 重置所有指示器為灰色
        self._bt_status_indicator.setStyleSheet("color: gray; font-size: 20px;")
        self._device_status_indicator.setStyleSheet("color: gray; font-size: 20px;")
        self._signal_status_indicator.setStyleSheet("color: gray; font-size: 20px;")
        self._strength_label.setText("💪 訊號強度: --")

    # --------------------------------------------------------- 動作記錄 --
    def _on_record_clicked(self) -> None:
        """處理記錄按鈕點擊"""
        if not self._recording:
            self._start_recording()
        else:
            self._stop_recording()
    
    def _start_recording(self) -> None:
        """開始記錄動作"""
        # 取得手勢標籤
        gesture = self._gesture_combo.currentText()
        if gesture == "custom":
            gesture = self._custom_label_input.text().strip()
            if not gesture:
                self._log("錯誤：請輸入自定義標籤")
                return
        
        # 初始化記錄器（如果尚未初始化）
        if self._motion_recorder is None:
            try:
                self._motion_recorder = MotionRecorder(
                    enable_camera=True,
                    camera_id=0
                )
                self._log("動作記錄器已初始化")
            except Exception as e:
                self._log(f"初始化記錄器失敗: {e}")
                return
        
        # 開始記錄
        if self._motion_recorder.start_recording(gesture):
            self._recording = True
            import time
            self._recording_start_time = time.time()
            
            # 更新 UI
            self._record_button.setText("■ 停止記錄")
            self._record_button.setStyleSheet("""
                QPushButton {
                    background-color: #4CD964;
                    color: white;
                    font-weight: bold;
                    padding: 8px 16px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #5AC8FA;
                }
            """)
            self._recording_status_label.setText(f"記錄中: {gesture}")
            self._recording_status_label.setStyleSheet("color: #FF3B30; font-weight: bold;")
            
            # 禁用其他控制
            self._gesture_combo.setEnabled(False)
            self._custom_label_input.setEnabled(False)
            self._disconnect_button.setEnabled(False)
            
            # 如果啟用攝影機，自動開啟預覽視窗
            if self._motion_recorder.enable_camera:
                if self._camera_preview is None:
                    # 不傳入 parent，創建獨立視窗
                    self._camera_preview = CameraPreviewWindow()
                self._camera_preview.show()
                self._camera_preview_button.setChecked(True)
                self._log("✅ 攝影機預覽已自動開啟")
            
            self._log(f"開始記錄動作: {gesture}")
        else:
            self._log("無法開始記錄")
    
    def _stop_recording(self) -> None:
        """停止記錄並儲存"""
        if not self._recording or self._motion_recorder is None:
            return
        
        # 生成檔案名稱
        import time
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        gesture = self._gesture_combo.currentText()
        if gesture == "custom":
            gesture = self._custom_label_input.text().strip()
        
        filename = f"recordings/motion_{gesture}_{timestamp}.npz"
        
        # 停止記錄並儲存
        if self._motion_recorder.stop_recording(filename):
            duration = time.time() - self._recording_start_time
            self._log(f"記錄完成: {filename} (時長: {duration:.2f}秒)")
            self._recording_status_label.setText(f"✓ 已儲存 ({duration:.1f}秒)")
            self._recording_status_label.setStyleSheet("color: #4CD964; font-weight: bold;")
        else:
            self._log("記錄儲存失敗")
            self._recording_status_label.setText("✗ 儲存失敗")
            self._recording_status_label.setStyleSheet("color: #FF3B30; font-weight: bold;")
        
        self._recording = False
        self._recording_time_label.setText("")
        
        # 關閉攝影機預覽視窗
        if self._camera_preview is not None and self._camera_preview.isVisible():
            self._camera_preview.hide()
            self._camera_preview_button.setChecked(False)
        
        # 恢復 UI
        self._record_button.setText("● 開始記錄")
        self._record_button.setStyleSheet("""
            QPushButton {
                background-color: #FF3B30;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #FF2D55;
            }
        """)
        
        self._gesture_combo.setEnabled(True)
        if self._gesture_combo.currentText() == "custom":
            self._custom_label_input.setEnabled(True)
        self._disconnect_button.setEnabled(True)
    
    def _on_camera_preview_clicked(self, checked: bool) -> None:
        """處理攝影機預覽按鈕"""
        if checked:
            # 檢查是否正在錄影
            if not self._motion_recorder or not self._motion_recorder.recording:
                self._log("⚠️ 請先開始錄影才能預覽攝影機")
                self._camera_preview_button.setChecked(False)
                return
            
            # 檢查攝影機是否啟用
            if not self._motion_recorder.enable_camera:
                self._log("⚠️ 攝影機未啟用")
                self._camera_preview_button.setChecked(False)
                return
            
            # 顯示攝影機預覽視窗
            if self._camera_preview is None:
                self._camera_preview = CameraPreviewWindow()
            
            self._camera_preview.show()
            self._log("✅ 攝影機預覽已開啟")
        else:
            # 隱藏攝影機預覽視窗
            if self._camera_preview is not None:
                self._camera_preview.hide()
            self._log("攝影機預覽已關閉")
