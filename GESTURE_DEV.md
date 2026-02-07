# 手勢識別功能開發指南

> **分支**: `feature/gesture-recognition`  
> **狀態**: 🚧 開發中  
> **基於**: v2.1 (b120a28)

## 📋 開發目標

實現基於 8 通道 EMG 訊號的手部動作識別系統，參考 Meta 的研究成果。

## 🎯 核心功能

### 1. 動作記錄系統
- [x] 專案結構建立
- [ ] MediaPipe 手部追蹤整合
- [ ] EMG + 攝影機同步錄製
- [ ] 資料儲存與管理
- [ ] UI 整合（錄製按鈕）

### 2. EMG 解碼器
- [ ] 訊號預處理管線
- [ ] 特徵提取模組
- [ ] LSTM/Transformer 模型
- [ ] 訓練腳本
- [ ] 模型評估工具

### 3. 虛擬手骨
- [ ] 3D 渲染引擎
- [ ] 即時動畫更新
- [ ] 動作比對顯示
- [ ] UI 整合

## 🛠️ 開發環境設置

### 安裝依賴
```bash
# 基礎依賴
pip install -r requirements.txt

# 手勢識別額外依賴
pip install -r requirements_gesture.txt
```

### 驗證安裝
```python
# test_imports.py
import cv2
import mediapipe as mp
import torch
import pyqtgraph.opengl as gl

print("✅ 所有依賴安裝成功！")
print(f"PyTorch 版本: {torch.__version__}")
print(f"CUDA 可用: {torch.cuda.is_available()}")
```

## 📂 檔案結構

```
handProject_1103/
├── emg_monitor/
│   ├── motion_recorder.py      # 🆕 待實作
│   ├── neuromotor_decoder.py   # 🆕 待實作
│   └── virtual_hand.py         # 🆕 待實作
│
├── recordings/                 # 訓練資料
│   ├── .gitkeep
│   ├── motion_20250103_143022.npz  # 範例
│   └── motion_20250103_143022.mp4
│
├── models/                     # 訓練模型
│   ├── .gitkeep
│   └── emg_decoder.pth         # 範例
│
├── scripts/                    # 🆕 待建立
│   ├── train_model.py          # 訓練腳本
│   ├── evaluate_model.py       # 評估工具
│   └── visualize_data.py       # 資料視覺化
│
├── requirements_gesture.txt    # ✅ 已建立
├── GESTURE_DEV.md             # ✅ 本檔案
└── README.md                   # ✅ 已更新
```

## 🚀 開發階段

### Phase 1: 資料收集 (當前階段)

**目標**: 建立訓練資料收集工具

**任務清單**:
- [ ] 實作 `motion_recorder.py`
  - [ ] MediaPipe 手部追蹤
  - [ ] 時間戳同步
  - [ ] 資料儲存格式
  
- [ ] 整合到 `main_window.py`
  - [ ] 新增錄製按鈕
  - [ ] 錄製狀態顯示
  - [ ] 檔案管理介面

- [ ] 測試與驗證
  - [ ] 時間戳準確性
  - [ ] 資料完整性
  - [ ] 記憶體使用

**預期產出**:
- 能夠同步錄製 EMG + 影像 + 手部骨架
- 儲存為標準格式 (.npz + .mp4)
- 收集至少 100 組不同手勢的資料

### Phase 2: 模型訓練

**目標**: 訓練 EMG → 手部姿態解碼器

**任務清單**:
- [ ] 資料預處理
  - [ ] 訊號濾波 (20-450 Hz)
  - [ ] RMS 包絡提取
  - [ ] 歸一化處理
  
- [ ] 模型架構
  - [ ] LSTM 基礎版本
  - [ ] Transformer 進階版本
  - [ ] 損失函數設計
  
- [ ] 訓練管線
  - [ ] 資料載入器
  - [ ] 訓練迴圈
  - [ ] 驗證與早停
  - [ ] 模型儲存

**預期產出**:
- 訓練好的解碼器模型 (.pth)
- 訓練日誌與曲線
- 評估報告 (精度、延遲)

### Phase 3: 即時推理

**目標**: 整合模型到即時系統

**任務清單**:
- [ ] 推理引擎
  - [ ] 模型載入
  - [ ] 滑動窗口管理
  - [ ] 批次推理優化
  
- [ ] 虛擬手骨
  - [ ] 3D 渲染引擎
  - [ ] 骨架動畫
  - [ ] 流暢度優化
  
- [ ] UI 整合
  - [ ] 顯示切換
  - [ ] 效能監控
  - [ ] 除錯工具

**預期產出**:
- 低延遲即時推理 (<50ms)
- 流暢的虛擬手骨顯示
- 完整的使用者介面

## 📊 資料格式規範

### EMG + 骨架資料 (.npz)

```python
data = {
    'timestamps': np.array([...]),      # (N,) 時間戳 (秒)
    'emg_data': np.array([...]),        # (N, 8) EMG 訊號 (μV)
    'landmarks': [                       # (N, 21, 3) 手部關鍵點
        np.array([[x, y, z], ...]),     # MediaPipe 座標 (歸一化 0-1)
        ...
    ],
    'metadata': {
        'sample_rate': 200,              # EMG 採樣率
        'duration': 10.5,                # 錄製時長 (秒)
        'camera_fps': 30,                # 攝影機幀率
        'subject_id': 'user001',         # 受試者 ID
        'gesture_label': 'fist',         # 手勢標籤
    }
}
```

### 訓練資料組織

```
recordings/
├── session_20250103/
│   ├── fist_001.npz        # 握拳動作
│   ├── fist_002.npz
│   ├── open_001.npz        # 張開手掌
│   ├── pinch_001.npz       # 捏取動作
│   └── ...
└── session_20250104/
    └── ...
```

## 🎓 技術參考

### Meta 研究論文
- [A Large-Scale Study of Wrist-Worn Gestures](https://research.facebook.com/publications/)
- [EMG-based Gesture Recognition for AR/VR](https://research.facebook.com/)

### GitHub 專案
- [generic-neuromotor-interface](https://github.com/facebookresearch/generic-neuromotor-interface)
- [emg2qwerty](https://github.com/facebookresearch/emg2qwerty)

### 關鍵技術
- **MediaPipe Hands**: 手部關鍵點偵測
- **LSTM/Transformer**: 時序建模
- **RMS 包絡**: EMG 特徵提取
- **滑動窗口**: 即時訊號處理

## 🐛 已知問題

| 問題 | 狀態 | 解決方案 |
|------|------|---------|
| 8 通道精度限制 | ⚠️ 需驗證 | 專注基本手勢，避免複雜動作 |
| 個體差異大 | ⚠️ 需研究 | 個人化訓練 + 線上適應 |
| 即時性要求 | 📋 待實作 | 輕量化模型 + GPU 加速 |

## 📝 開發日誌

### 2025-11-03
- ✅ 創建 `feature/gesture-recognition` 分支
- ✅ 更新 README 說明
- ✅ 建立專案結構
- ✅ 準備依賴清單
- 📋 下一步：實作 `motion_recorder.py`

## 💡 貢獻指南

1. **保持分支獨立**: 不影響 main 分支的穩定性
2. **小步提交**: 每個功能模組獨立提交
3. **測試先行**: 新功能必須有測試
4. **文件同步**: 更新對應的開發文檔

## 📞 聯絡方式

如有問題或建議，歡迎：
- 開 Issue 討論
- 提交 Pull Request
- 直接聯繫專案維護者

---

**最後更新**: 2025-11-03  
**維護者**: akaiHuang
