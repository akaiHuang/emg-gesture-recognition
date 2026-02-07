"""Central configuration for the EMG monitor app."""

DEFAULT_NOTIFICATION_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
DEFAULT_SCAN_TIMEOUT = 5.0
EMG_CHANNELS = 8
BUFFER_SECONDS = 1  # 降至 1 秒以減少繪圖負擔（200 點 vs 400 點）
SAMPLE_RATE_HZ = 200  # 實際採樣率約 200Hz（每秒 200 個封包）
