#!/bin/bash
# 同時啟動 EMG Monitor 和效能監控

SCRIPT_DIR="/Users/akaihuangm1/Desktop/handProject_1103"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"

echo "🚀 正在啟動 EMG Monitor..."
echo ""

# 在背景啟動主程式
$VENV_PYTHON "$SCRIPT_DIR/main.py" &
MAIN_PID=$!

echo "✅ EMG Monitor 已啟動 (PID: $MAIN_PID)"
echo "⏳ 等待程式初始化..."
sleep 3

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 開始效能監控（每 2 秒更新）"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "按 Ctrl+C 停止監控和程式"
echo ""

# 捕捉 Ctrl+C 並清理
trap 'echo ""; echo "🛑 正在停止..."; kill $MAIN_PID 2>/dev/null; exit' INT TERM

# 監控循環
while kill -0 $MAIN_PID 2>/dev/null; do
    clear
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           EMG Monitor 效能監控                              ║"
    echo "║           時間: $(date '+%Y-%m-%d %H:%M:%S')                         ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    
    # 檢查程式是否還在運行
    if ! kill -0 $MAIN_PID 2>/dev/null; then
        echo "⚠️  程式已停止"
        break
    fi
    
    # CPU 和記憶體
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 Python 進程 (PID: $MAIN_PID)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ps -p $MAIN_PID -o %cpu,%mem,rss,vsz | tail -1 | awk '{
        rss_mb = $3 / 1024
        vsz_mb = $4 / 1024
        printf "  CPU: %6.1f%%  |  MEM: %5.1f%%  |  RSS: %.0f MB  |  VSZ: %.0f MB\n", $1, $2, rss_mb, vsz_mb
    }'
    
    echo ""
    
    # 系統整體 CPU
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "💻 系統 CPU"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    top -l 1 | grep "CPU usage" | awk '{
        printf "  User: %s  |  Sys: %s  |  Idle: %s\n", $3, $5, $7
    }'
    
    echo ""
    
    # 線程數
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🧵 線程"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    THREAD_COUNT=$(ps -M $MAIN_PID 2>/dev/null | tail -n +2 | wc -l | awk '{print $1}')
    echo "  線程數: $THREAD_COUNT"
    
    echo ""
    
    # GPU 提示
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🎮 GPU (需要 sudo 查看詳細)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  使用以下命令查看 GPU 使用率："
    echo "  sudo powermetrics --samplers gpu_power -i 2000 -n 1"
    
    echo ""
    
    # 效能評估
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "💡 效能評估"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    CPU=$(ps -p $MAIN_PID -o %cpu | tail -1 | awk '{print $1}')
    CPU_INT=$(echo "$CPU" | cut -d. -f1)
    
    if [ "$CPU_INT" -lt 40 ]; then
        echo "  ✅ 優秀 - CPU 使用率正常 (<40%)"
    elif [ "$CPU_INT" -lt 70 ]; then
        echo "  ⚠️  中等 - CPU 使用率偏高 (40-70%)"
    else
        echo "  ❌ 需優化 - CPU 使用率過高 (>70%)"
    fi
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    sleep 2
done

echo ""
echo "✅ 監控結束"
