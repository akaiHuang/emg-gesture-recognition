# 動作記錄功能使用說明

## 🎬 功能概述

EMG Monitor 整合了動作記錄功能，可以**同步記錄 EMG 訊號、攝影機影像和手部 21 個關鍵點**，用於建立手勢識別訓練資料集。

### � 時間戳同步機制

**重要：** 系統自動確保 EMG 資料、影片和手部骨架完全同步：

1. **統一時間基準**：記錄開始時設定 `start_time`，所有資料使用相對時間戳（秒）
2. **幀同步**：每次收到 EMG 樣本（200 Hz）時：
   - 讀取攝影機當前幀（30 fps）
   - 執行 MediaPipe 手部追蹤（21 個關鍵點）
   - 計算時間戳：`timestamp = 當前時間 - start_time`
   - 將三者打包成一個 `MotionFrame` 儲存
3. **完美對應**：同一個 timestamp 對應同一組 EMG 數據、影片幀、手部骨架

**結果：** 你可以根據時間戳，精確對應任何時刻的 EMG 訊號和手部動作！

## �📋 使用步驟

### 1. 連接 EMG 裝置

首先需要連接 EMG 裝置（藍牙或 USB 序列埠），確保能正常接收 EMG 訊號。

### 2. 選擇手勢標籤

在「動作記錄」區域的下拉選單中選擇要記錄的手勢：

- **fist**: 握拳
- **open**: 張開手掌
- **pinch**: 捏取動作
- **thumbs_up**: 豎起大拇指
- **peace**: 比YA
- **pointing**: 食指指向
- **wave**: 揮手
- **rest**: 休息/放鬆狀態
- **custom**: 自定義標籤（需要在旁邊的輸入框填寫）

### 3. 開始記錄

1. 點擊「● 開始記錄」按鈕
2. **攝影機自動開啟**並開始追蹤手部
3. 按鈕會變成綠色「■ 停止記錄」
4. 開始執行你選擇的手勢動作
5. 記錄時間會即時顯示（例如：1.5s, 2.0s...）

**建議記錄時長：** 每個手勢 3-5 秒

### 4. 停止記錄

1. 點擊「■ 停止記錄」按鈕
2. **攝影機自動關閉**
3. 資料會自動儲存到 `recordings/` 目錄
4. 檔案命名格式：`motion_{手勢}_{時間戳}.npz` 和 `.mp4`
   - 例如：`motion_fist_20251104_010203.npz`
   - 例如：`motion_fist_20251104_010203.mp4`（含手部骨架疊加）

### 5. 查看儲存的資料

記錄完成後，會在 `recordings/` 目錄中看到：
- **`.npz` 檔案**：壓縮的 NumPy 資料包，包含所有同步資料
- **`.mp4` 檔案**：影片記錄，畫面上疊加了 21 個手部關鍵點

## 📊 資料格式詳解

### `.npz` 是什麼？

`.npz` 是 **NumPy 壓縮資料格式**（ZIP 打包的 `.npy` 檔案），可以在一個檔案中儲存多個 numpy 陣列和字典。

### 檔案內容結構

```python
{
    'timestamps': numpy.ndarray,      # shape: (N,) - 每個樣本的時間戳（秒）
    'emg_data': numpy.ndarray,        # shape: (N, 8) - N 個樣本 × 8 通道 EMG 資料（μV）
    'landmarks': numpy.ndarray,       # shape: (N, 21, 3) - N 個樣本 × 21 個關鍵點 × XYZ 座標
    'landmarks_valid': numpy.ndarray, # shape: (N,) - 布林陣列，標記哪些幀有偵測到手
    'metadata': dict                  # 元資料字典
}
```

### 資料詳細說明

**1. `timestamps` - 時間戳陣列**
- 類型：`numpy.ndarray`, dtype: `float32`
- Shape: `(N,)` where N = 樣本數
- 單位：秒（相對於記錄開始時間）
- 範例：`[0.0, 0.005, 0.010, 0.015, ...]` (200 Hz → 每 5ms 一個樣本)

**2. `emg_data` - EMG 訊號資料**
- 類型：`numpy.ndarray`, dtype: `float32`
- Shape: `(N, 8)` 
  - N = 時間樣本數
  - 8 = EMG 通道數
- 單位：微伏特（μV）
- 採樣率：200 Hz
- 範例：
  ```python
  [[123.4, 234.5, 345.6, ..., 890.1],  # t=0.000s 的 8 通道數據
   [124.1, 235.2, 346.3, ..., 891.0],  # t=0.005s 的 8 通道數據
   ...]
  ```

**3. `landmarks` - 手部關鍵點座標**
- 類型：`numpy.ndarray`, dtype: `float32`
- Shape: `(N, 21, 3)`
  - N = 時間樣本數（與 EMG 對應）
  - 21 = MediaPipe 手部關鍵點數量
  - 3 = XYZ 座標（歸一化到 0-1 範圍）
- 座標系統：
  - X: 水平方向（0=左, 1=右）
  - Y: 垂直方向（0=上, 1=下）
  - Z: 深度方向（相對於手腕，單位：像素寬度）
- 關鍵點編號（MediaPipe Hands）：
  ```
  0:  手腕 (WRIST)
  1-4:  大拇指 (THUMB_CMC, MCP, IP, TIP)
  5-8:  食指 (INDEX_FINGER_MCP, PIP, DIP, TIP)
  9-12: 中指 (MIDDLE_FINGER_MCP, PIP, DIP, TIP)
  13-16: 無名指 (RING_FINGER_MCP, PIP, DIP, TIP)
  17-20: 小指 (PINKY_MCP, PIP, DIP, TIP)
  ```
- 特殊情況：若該幀未偵測到手，則填充全零 `np.zeros((21, 3))`

**4. `landmarks_valid` - 偵測有效性標記**
- 類型：`numpy.ndarray`, dtype: `bool`
- Shape: `(N,)`
- 含義：`True` = 該幀成功偵測到手，`False` = 未偵測到（landmarks 為全零）
- 用途：訓練時可以過濾掉無效幀

**5. `metadata` - 元資料字典**
```python
{
    'gesture_label': str,        # 手勢標籤（如 "fist", "open"）
    'sample_rate': int,          # EMG 採樣率（200 Hz）
    'camera_enabled': bool,      # 是否啟用攝影機
    'camera_fps': int,           # 攝影機幀率（30 fps）
    'start_time': str,           # 記錄開始時間（格式："2025-11-04 01:02:03"）
    'duration': float,           # 記錄時長（秒）
    'num_frames': int            # 總幀數
}
```

### 讀取範例

```python
import numpy as np

# 載入資料
data = np.load('recordings/motion_fist_20251104_010203.npz', allow_pickle=True)

# 存取各項資料
timestamps = data['timestamps']        # 時間戳
emg_data = data['emg_data']           # EMG 訊號
landmarks = data['landmarks']          # 手部關鍵點
landmarks_valid = data['landmarks_valid']  # 偵測有效性
metadata = data['metadata'].item()     # 元資料（需要 .item() 轉成字典）

# 範例：顯示資訊
print(f"手勢：{metadata['gesture_label']}")
print(f"時長：{metadata['duration']:.2f} 秒")
print(f"樣本數：{len(timestamps)}")
print(f"EMG shape: {emg_data.shape}")          # 應該是 (N, 8)
print(f"Landmarks shape: {landmarks.shape}")   # 應該是 (N, 21, 3)
print(f"有效偵測率：{landmarks_valid.sum() / len(landmarks_valid) * 100:.1f}%")

# 範例：找出特定時間點的資料
target_time = 1.5  # 記錄開始後 1.5 秒
idx = np.argmin(np.abs(timestamps - target_time))
print(f"\n時間點 {timestamps[idx]:.3f}s 的資料：")
print(f"EMG 通道 0: {emg_data[idx, 0]:.2f} μV")
if landmarks_valid[idx]:
    print(f"手腕位置 (x,y,z): {landmarks[idx, 0]}")  # 關鍵點 0 = 手腕
else:
    print("此時刻未偵測到手")
```

### 時間戳對應關係

**關鍵概念：** 所有陣列的第一維度（索引 `i`）對應同一個時間點：

```python
# 假設 i = 100（第 100 個樣本）
time_point = timestamps[100]       # 例如：0.500 秒
emg_at_time = emg_data[100]        # 該時刻的 8 通道 EMG
hand_at_time = landmarks[100]      # 該時刻的 21 個關鍵點
is_hand_detected = landmarks_valid[100]  # 是否偵測到手

# 完美同步！可以精確分析任何時刻的 EMG 訊號對應的手部動作
```

## 💡 使用技巧

### 建立良好的訓練資料集

1. **每種手勢記錄多次**
   - 建議：每個手勢至少 10-20 次
   - 在不同時間、不同狀態下記錄

2. **保持動作一致性**
   - 記錄時盡量保持動作穩定
   - 從開始到結束維持相同的姿勢

3. **包含過渡狀態**
   - 記錄從「rest」到目標手勢的過程
   - 記錄手勢之間的切換

4. **記錄「rest」狀態**
   - 這是重要的負樣本
   - 幫助模型區分「動作」和「靜止」

### 資料收集計劃範例

```
第一階段（基礎手勢）：
- fist × 20 次
- open × 20 次  
- rest × 20 次

第二階段（進階手勢）：
- pinch × 15 次
- thumbs_up × 15 次
- pointing × 15 次

第三階段（複雜動作）：
- wave × 10 次
- peace × 10 次
```

## 🔧 故障排除

### 問題：攝影機無法開啟

**原因：** macOS 需要授權攝影機權限

**解決方案：**
1. 前往「系統偏好設定」→「安全性與隱私」→「相機」
2. 確認 Terminal.app 或 Python 有攝影機權限
3. 重新啟動應用程式

### 問題：MediaPipe 未安裝

**原因：** Python 3.13 不支援 MediaPipe

**解決方案：**
- 已使用 Python 3.11 虛擬環境
- 如果仍有問題，執行：
  ```bash
  pip install mediapipe>=0.10.0
  ```

### 問題：記錄按鈕無法點擊

**原因：** 裝置未連接

**解決方案：**
1. 確認已連接 EMG 裝置
2. 確認正在接收 EMG 訊號（觀察示波器）
3. 記錄按鈕會在連接後自動啟用

## 📁 檔案管理

### 檢視記錄的資料

```python
import numpy as np

# 載入資料
data = np.load('recordings/motion_fist_20251104_010203.npz', allow_pickle=True)

print(f"時間戳數量: {len(data['timestamps'])}")
print(f"EMG 資料形狀: {data['emg_data'].shape}")
print(f"手部關鍵點形狀: {data['landmarks'].shape}")

# 讀取元資料
metadata = data['metadata'].item()
print(f"手勢標籤: {metadata['gesture_label']}")
print(f"記錄時長: {metadata['duration']:.2f} 秒")
```

### 清理測試資料

```bash
# 刪除所有記錄
rm -rf recordings/*.npz recordings/*.mp4

# 只保留 .gitkeep
```

## 🚀 下一步

收集足夠的資料後，你可以：

1. **訓練手勢分類器**
   - 使用 PyTorch 訓練 LSTM 模型
   - 輸入：8 通道 EMG 時序資料
   - 輸出：手勢類別

2. **建立即時識別系統**
   - 整合訓練好的模型到 UI
   - 顯示即時手勢預測

3. **3D 手部可視化**
   - 使用 MediaPipe 關鍵點
   - 繪製 3D 手部骨架

4. **應用場景**
   - 遊戲控制
   - 虛擬實境互動
   - 輔助設備控制

---

## 📞 支援

如有問題，請參考：
- `GESTURE_DEV.md`：詳細開發指南
- `motion_recorder.py`：記錄器原始碼
- `test_mediapipe.py`：獨立測試腳本
