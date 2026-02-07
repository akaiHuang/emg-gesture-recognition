# CH1~CH8 訊號精準度改進說明

## 問題診斷

原程式碼的問題在於：

1. **基線追蹤過於激進**：基線會持續追蹤訊號變化，即使是其他通道的活動也會影響未觸碰通道的基線
2. **噪音水平計算不準確**：包含了變化率（change_rate），導致閾值設定不精確
3. **閾值設定過低**：2.5倍噪音就判定為活躍，容易受串擾影響

## 修正內容

### 1. 改進基線更新策略（`main_window.py` 第 367-377 行）

**修正前：**
```python
# 自適應更新速率 - 即使中等訊號也會持續更新基線
if deviation < self._channel_noise_level[i] * 2:
    alpha = 0.02  # 快速更新
elif deviation < self._channel_noise_level[i] * 5:
    alpha = 0.002  # 中速更新
else:
    alpha = 0.0001  # 極慢更新
self._channel_baseline[i] = alpha * ch_value + (1 - alpha) * self._channel_baseline[i]
```

**修正後：**
```python
# 只在真正待機時更新基線
if deviation < self._channel_noise_level[i] * 1.5:
    # 只有非常接近基線時才更新（1.5倍噪音以內）
    alpha = 0.01
    self._channel_baseline[i] = alpha * ch_value + (1 - alpha) * self._channel_baseline[i]
# 否則：完全不更新基線
```

**改進效果：**
- 基線只追蹤「靜止狀態」，不會被訊號變化帶走
- 未觸碰的通道基線保持穩定，不受其他通道影響

### 2. 修正噪音水平計算（`main_window.py` 第 315-321 行）

**修正前：**
```python
deviation = abs(ch_value - self._channel_baseline[i])
change_rate = abs(ch_value - self._channel_last_values[i])
activity = (deviation * 0.7 + change_rate * 0.3)  # 混合計算
self._channel_noise_level[i] += activity
```

**修正後：**
```python
deviation = abs(ch_value - self._channel_baseline[i])
# 只計算偏離值，不包含變化率
self._channel_noise_level[i] += deviation
```

**改進效果：**
- 噪音水平更準確反映「待機時的自然波動」
- 閾值設定更精確，不會被瞬間變化誤導

### 3. 提高活躍判定閾值（`main_window.py` 第 430-438 行）

**修正前：**
```python
thresholds = {
    0: (0, noise_baseline * 2.5),           # 2.5倍噪音 -> 正常
    1: (noise_baseline * 2.0, noise_baseline * 4.0),
    2: (noise_baseline * 3.5, noise_baseline * 6.0),
    3: (noise_baseline * 5.5, 999999)
}
```

**修正後：**
```python
thresholds = {
    0: (0, noise_baseline * 3.5),           # 3.5倍噪音 -> 正常（提高40%）
    1: (noise_baseline * 3.0, noise_baseline * 6.0),
    2: (noise_baseline * 5.0, noise_baseline * 10.0),
    3: (noise_baseline * 8.0, 999999)
}
```

**改進效果：**
- 只有真正觸碰的通道才會觸發（需要超過3.5倍基線噪音）
- 大幅降低串擾誤判

## 測試建議

1. **連接裝置後等待 2.5 秒**（500 個封包）讓基線初始化完成
2. **觀察待機狀態**：所有通道應顯示「待機」（灰色）
3. **單獨觸碰 CH1**：只有 CH1 應該變色，其他通道保持灰色
4. **依序測試 CH2~CH8**：每次只有被觸碰的通道有反應
5. **查看終端輸出**：活躍通道數應該是 1（除非真的同時觸碰多個電極）

## 預期效果

- ✅ 只有被觸碰的通道會顯示訊號（黃色/綠色/紅色）
- ✅ 未觸碰的通道保持灰色「待機」狀態
- ✅ 終端輸出顯示「活躍通道數: 1」（單通道測試時）
- ✅ 串擾警告大幅減少

## 如需進一步調整

如果仍有輕微串擾，可以繼續提高閾值：
- 在 `main_window.py` 第 433 行，將 `3.5` 改為 `4.0` 或 `4.5`
- 重新啟動程式讓基線重新初始化

## 技術原理

EMG 訊號的通道隔離關鍵在於：
1. **基線穩定性**：只在待機時更新，避免被訊號變化影響
2. **閾值設定**：基於「靜止時的自然噪音」而非「包含動作的整體變化」
3. **遲滯機制**：避免在閾值邊緣反覆跳動

這次修正讓程式更符合生理訊號的特性！
