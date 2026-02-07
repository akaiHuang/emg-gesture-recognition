# 效能優化說明

## 啟動速度優化

### 問題
- MediaPipe 內部依賴 matplotlib
- matplotlib 首次 import 時會掃描系統所有字體（macOS 上特別慢）
- 原本啟動需要 15+ 秒

### 解決方案：背景非同步載入

#### 1. 延遲載入（Lazy Import）
```python
# motion_recorder.py
_mp_module = None  # 全域變數，避免重複載入

def _lazy_import_mediapipe():
    """只在需要時才載入 MediaPipe"""
    global _mp_module
    if _mp_module is None:
        import mediapipe as mp
        _mp_module = mp
    return _mp_module
```

#### 2. 非同步背景載入
```python
async def _async_import_mediapipe():
    """在背景執行緒中載入，不阻塞 UI"""
    loop = asyncio.get_event_loop()
    mp_module, success = await loop.run_in_executor(
        None, 
        _load_in_thread  # 在執行緒池中執行
    )
    return success
```

#### 3. UI 整合
```python
# main_window.py
def __init__(self):
    # ... 建立 UI
    
    # 啟動後 100ms 開始背景載入
    QtCore.QTimer.singleShot(
        100, 
        lambda: asyncio.create_task(self._preload_mediapipe())
    )
    
async def _preload_mediapipe(self):
    """背景載入 MediaPipe"""
    self._log("🔄 開始在背景載入 MediaPipe（這可能需要 10-15 秒）...")
    success = await mr._async_import_mediapipe()
    if success:
        self._mediapipe_ready = True
        self._log("✅ MediaPipe 載入完成！現在可以開始錄影")
        self._record_button.setEnabled(True)  # 啟用錄影按鈕
```

### 效果

| 項目 | 優化前 | 優化後 |
|------|--------|--------|
| 視窗啟動 | 15+ 秒 | **0.5 秒** ⚡️ |
| MediaPipe 載入 | 阻塞 UI | 背景載入，不影響操作 |
| 錄影按鈕 | 啟動時可用 | 載入完成後才可用（更安全） |

### 使用者體驗

1. **立即啟動**：點擊應用程式後 0.5 秒內視窗就出現
2. **即時回饋**：日誌顯示「🔄 開始在背景載入 MediaPipe...」
3. **正常使用**：可以立即連接裝置、查看 EMG 訊號
4. **錄影就緒**：10-15 秒後顯示「✅ MediaPipe 載入完成」，錄影按鈕變為可用

### 技術細節

#### 為什麼 MediaPipe 依賴 matplotlib？
MediaPipe 的 `drawing_utils.py` 模組用 matplotlib 繪製 3D 手部骨架視覺化。雖然我們的程式不需要這個功能（只需要關鍵點座標），但 MediaPipe 在 import 時會自動載入所有模組。

#### matplotlib 字體掃描做什麼？
1. 呼叫 `system_profiler -xml SPFontsDataType` 讀取所有系統字體
2. 在 macOS 上有數百個字體，掃描需要 10+ 秒
3. 建立字體快取 `.matplotlib/fontlist-*.json`

#### 為什麼不能直接跳過字體掃描？
試過多種方法：
- ❌ 設定 `MPLBACKEND=Agg`（無效，還是會掃描）
- ❌ 猴子補丁 `font_manager.findSystemFonts`（時機太晚）
- ❌ 只 import `mediapipe.python.solutions.hands`（還是會觸發）
- ✅ **非同步載入**是最可靠的解決方案

### 程式碼位置

- `emg_monitor/motion_recorder.py`: 
  - `_lazy_import_mediapipe()` - 同步載入
  - `_async_import_mediapipe()` - 非同步載入
  - `is_mediapipe_ready()` - 檢查載入狀態
  - `is_mediapipe_loading()` - 檢查是否載入中

- `emg_monitor/ui/main_window.py`:
  - `__init__()` - 使用 QTimer 觸發背景載入
  - `_preload_mediapipe()` - 非同步載入並更新 UI
  - `_set_controls_enabled()` - 根據載入狀態控制按鈕

### 未來改進

1. **首次載入快取**：第二次啟動時 matplotlib 字體快取已存在，載入會更快
2. **可選安裝**：如果不需要錄影功能，可以不安裝 MediaPipe
3. **進度顯示**：顯示載入進度條（目前只有開始/完成訊息）
