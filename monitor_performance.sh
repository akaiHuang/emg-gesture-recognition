#!/bin/bash
# EMG Monitor 完整效能監控腳本
# 監控 CPU、GPU、記憶體使用情況

echo "=== EMG Monitor 效能監控 ==="
echo "按 Ctrl+C 停止監控"
echo ""

while true; do
    clear
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           EMG Monitor 即時效能監控                          ║"
    echo "║           時間: $(date '+%Y-%m-%d %H:%M:%S')                         ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    
    # 檢查程式是否運行
    PID=$(pgrep -f "python.*main.py" | head -1)
    
    if [ -z "$PID" ]; then
        echo "⚠️  EMG Monitor 未運行"
        echo ""
        echo "請先啟動程式："
        echo "  /Users/akaihuangm1/Desktop/handProject_1103/.venv/bin/python main.py"
        sleep 2
        continue
    fi
    
    echo "✅ 程式運行中 (PID: $PID)"
    echo ""
    
    # CPU 和記憶體
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 CPU & 記憶體"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ps aux | grep "[p]ython.*main.py" | awk '{
        printf "  CPU: %6.1f%% | MEM: %5.1f%% (%s)\n", $3, $4, $6
    }'
    
    # 系統整體 CPU
    echo ""
    top -l 1 | grep "CPU usage" | awk '{
        printf "  系統 CPU: User %s | Sys %s | Idle %s\n", $3, $5, $7
    }'
    
    echo ""
    
    # GPU 使用率（需要 sudo）
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🎮 GPU (Apple Silicon)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # 使用 ioreg 獲取 GPU 資訊（不需要 sudo）
    GPU_INFO=$(ioreg -r -d 1 -w 0 -c "IOAccelerator" 2>/dev/null | grep "PerformanceStatistics" | head -1)
    if [ -n "$GPU_INFO" ]; then
        echo "  ✅ GPU 活躍"
    else
        echo "  ℹ️  GPU 資訊不可用（需要 sudo powermetrics 查看詳細資訊）"
    fi
    
    echo ""
    
    # 記憶體詳細資訊
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "💾 記憶體使用情況"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # 使用 vm_stat 獲取記憶體資訊
    vm_stat | awk '
        /Pages free/ { free = $3 }
        /Pages active/ { active = $3 }
        /Pages inactive/ { inactive = $3 }
        /Pages wired/ { wired = $4 }
        END {
            gsub(/\./, "", free)
            gsub(/\./, "", active)
            gsub(/\./, "", inactive)
            gsub(/\./, "", wired)
            
            page_size = 4096
            total_mb = (free + active + inactive + wired) * page_size / 1024 / 1024
            used_mb = (active + wired) * page_size / 1024 / 1024
            
            printf "  已使用: %.0f MB / 總計: %.0f MB\n", used_mb, total_mb
            printf "  使用率: %.1f%%\n", (used_mb / total_mb) * 100
        }
    '
    
    echo ""
    
    # 線程資訊
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🧵 線程資訊"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    ps -M $PID 2>/dev/null | tail -n +2 | wc -l | awk '{printf "  線程數: %d\n", $1}'
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "💡 提示："
    echo "  - CPU 應該 <50% 為佳"
    echo "  - 記憶體應該穩定，不持續增長"
    echo "  - 使用 'sudo powermetrics --samplers gpu_power -i 2000 -n 1'"
    echo "    可查看詳細的 GPU 使用率"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    sleep 2
done
