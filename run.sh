#!/bin/bash
# EMG Monitor 啟動腳本 - 優化 matplotlib 載入速度

# 設定 matplotlib 環境變數（必須在 Python 執行前）
export MPLBACKEND=Agg
export MPLCONFIGDIR=$(mktemp -d)

# 啟動應用程式
/Users/akaihuangm1/Desktop/handProject_1103/.venv/bin/python /Users/akaihuangm1/Desktop/handProject_1103/main.py

# 清理臨時快取
rm -rf "$MPLCONFIGDIR"
