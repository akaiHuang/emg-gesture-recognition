#!/usr/bin/env python3
"""檢查程式執行時的 CPU 使用率"""

import subprocess
import time
import sys

def get_python_process_cpu():
    """獲取所有 Python 進程的 CPU 使用率"""
    try:
        # 使用 ps 命令獲取 Python 進程資訊
        cmd = "ps aux | grep '[p]ython.*main.py'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0 and result.stdout:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                parts = line.split()
                if len(parts) >= 3:
                    cpu_percent = parts[2]  # CPU%
                    mem_percent = parts[3]  # MEM%
                    pid = parts[1]
                    return {
                        'pid': pid,
                        'cpu': float(cpu_percent),
                        'mem': float(mem_percent)
                    }
    except Exception as e:
        print(f"錯誤: {e}")
    
    return None

def monitor_performance(duration=10, interval=1):
    """監控程式效能
    
    Args:
        duration: 監控時長（秒）
        interval: 採樣間隔（秒）
    """
    print("=" * 60)
    print("🔍 EMG Monitor 效能監控")
    print("=" * 60)
    print(f"監控時長: {duration} 秒 | 採樣間隔: {interval} 秒")
    print("-" * 60)
    
    cpu_samples = []
    mem_samples = []
    
    for i in range(duration):
        info = get_python_process_cpu()
        
        if info:
            cpu_samples.append(info['cpu'])
            mem_samples.append(info['mem'])
            
            print(f"[{i+1:2d}s] PID: {info['pid']} | "
                  f"CPU: {info['cpu']:5.1f}% | "
                  f"MEM: {info['mem']:5.1f}%")
        else:
            print(f"[{i+1:2d}s] ⚠️ 未找到 main.py 進程")
        
        time.sleep(interval)
    
    print("-" * 60)
    
    if cpu_samples:
        avg_cpu = sum(cpu_samples) / len(cpu_samples)
        max_cpu = max(cpu_samples)
        avg_mem = sum(mem_samples) / len(mem_samples)
        
        print(f"\n📊 統計結果:")
        print(f"  平均 CPU: {avg_cpu:.1f}%")
        print(f"  最高 CPU: {max_cpu:.1f}%")
        print(f"  平均記憶體: {avg_mem:.1f}%")
        
        # 效能評估
        print(f"\n💡 效能評估:")
        if avg_cpu < 30:
            print("  ✅ 優秀 - CPU 使用率低，效能良好")
        elif avg_cpu < 50:
            print("  ⚠️ 中等 - CPU 使用率適中")
        else:
            print("  ❌ 需優化 - CPU 使用率偏高")
    else:
        print("\n⚠️ 未能收集到效能數據，請確認程式正在運行")
    
    print("=" * 60)

if __name__ == "__main__":
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    monitor_performance(duration=duration)
