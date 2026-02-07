#!/usr/bin/env python3
"""
效能分析工具 - 記錄三個階段的 CPU/GPU/記憶體使用
階段一：未連接（只有 UI）
階段二：已連接（接收 EMG 資料）
階段三：開啟攝影機（完整運作）
"""
import subprocess
import time
import json
import os
from datetime import datetime
from pathlib import Path


class PerformanceProfiler:
    def __init__(self):
        self.results = {
            "phase1_idle": [],
            "phase2_connected": [],
            "phase3_camera": []
        }
        self.pid = None
        self.output_dir = Path("performance_logs")
        self.output_dir.mkdir(exist_ok=True)
        
    def find_process(self):
        """找到 main.py 的 PID"""
        try:
            result = subprocess.run(
                ["pgrep", "-f", "python.*main.py"],
                capture_output=True,
                text=True
            )
            if result.stdout.strip():
                self.pid = int(result.stdout.strip().split()[0])
                return True
            return False
        except:
            return False
    
    def get_cpu_usage(self):
        """取得 CPU 使用率"""
        if not self.pid:
            return None
        try:
            result = subprocess.run(
                ["ps", "-p", str(self.pid), "-o", "%cpu"],
                capture_output=True,
                text=True
            )
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                return float(lines[1].strip())
        except:
            return None
    
    def get_memory_usage(self):
        """取得記憶體使用 (MB)"""
        if not self.pid:
            return None
        try:
            result = subprocess.run(
                ["ps", "-p", str(self.pid), "-o", "rss"],
                capture_output=True,
                text=True
            )
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                kb = int(lines[1].strip())
                return kb / 1024  # 轉換為 MB
        except:
            return None
    
    def get_thread_count(self):
        """取得線程數量"""
        if not self.pid:
            return None
        try:
            result = subprocess.run(
                ["ps", "-M", "-p", str(self.pid)],
                capture_output=True,
                text=True
            )
            # 計算線程數（排除標題行）
            lines = result.stdout.strip().split('\n')
            return len(lines) - 1 if len(lines) > 1 else 0
        except:
            return None
    
    def get_gpu_usage(self):
        """取得 GPU 使用率（需要 sudo）"""
        try:
            result = subprocess.run(
                ["sudo", "powermetrics", "--samplers", "gpu_power", "-i", "500", "-n", "1"],
                capture_output=True,
                text=True,
                timeout=3
            )
            output = result.stdout
            
            # 解析 GPU 資訊
            gpu_data = {}
            for line in output.split('\n'):
                if "GPU HW active residency:" in line:
                    # 提取使用率百分比
                    parts = line.split(':')
                    if len(parts) > 1:
                        usage_str = parts[1].strip().split()[0]
                        gpu_data['usage'] = float(usage_str.rstrip('%'))
                elif "GPU HW active frequency:" in line:
                    parts = line.split(':')
                    if len(parts) > 1:
                        freq_str = parts[1].strip().split()[0]
                        gpu_data['frequency'] = int(freq_str)
                elif "GPU Power:" in line:
                    parts = line.split(':')
                    if len(parts) > 1:
                        power_str = parts[1].strip().split()[0]
                        gpu_data['power_mw'] = int(power_str)
            
            return gpu_data if gpu_data else None
        except:
            return None
    
    def collect_sample(self):
        """收集一次效能數據"""
        sample = {
            "timestamp": datetime.now().isoformat(),
            "cpu_percent": self.get_cpu_usage(),
            "memory_mb": self.get_memory_usage(),
            "threads": self.get_thread_count(),
            "gpu": self.get_gpu_usage()
        }
        return sample
    
    def print_sample(self, sample, phase_name):
        """顯示即時數據"""
        cpu = sample['cpu_percent']
        mem = sample['memory_mb']
        threads = sample['threads']
        gpu = sample['gpu']
        
        print(f"\n{'='*60}")
        print(f"📊 階段：{phase_name}")
        print(f"⏰ 時間：{sample['timestamp'].split('T')[1].split('.')[0]}")
        print(f"{'='*60}")
        print(f"🔥 CPU:     {cpu:.1f}%" if cpu else "🔥 CPU:     N/A")
        print(f"💾 記憶體:  {mem:.1f} MB" if mem else "💾 記憶體:  N/A")
        print(f"🧵 線程數:  {threads}" if threads else "🧵 線程數:  N/A")
        
        if gpu:
            print(f"🎮 GPU:")
            print(f"   使用率:  {gpu.get('usage', 'N/A')}%")
            print(f"   頻率:    {gpu.get('frequency', 'N/A')} MHz")
            print(f"   功耗:    {gpu.get('power_mw', 'N/A')} mW")
        else:
            print(f"🎮 GPU:     需要 sudo 權限")
    
    def monitor_phase(self, phase_name, phase_key, duration=30, interval=2):
        """監控一個階段"""
        print(f"\n{'='*60}")
        print(f"🎯 開始監控：{phase_name}")
        print(f"⏱️  持續時間：{duration} 秒，採樣間隔：{interval} 秒")
        print(f"{'='*60}")
        
        start_time = time.time()
        sample_count = 0
        
        while time.time() - start_time < duration:
            if not self.find_process():
                print("\n⚠️  找不到程式！請確認程式正在運行。")
                return False
            
            sample = self.collect_sample()
            self.results[phase_key].append(sample)
            self.print_sample(sample, phase_name)
            sample_count += 1
            
            time.sleep(interval)
        
        print(f"\n✅ {phase_name} 監控完成！共收集 {sample_count} 個樣本")
        return True
    
    def calculate_stats(self, samples):
        """計算統計數據"""
        if not samples:
            return None
        
        cpu_values = [s['cpu_percent'] for s in samples if s['cpu_percent'] is not None]
        mem_values = [s['memory_mb'] for s in samples if s['memory_mb'] is not None]
        thread_values = [s['threads'] for s in samples if s['threads'] is not None]
        gpu_values = [s['gpu']['usage'] for s in samples if s['gpu'] and 'usage' in s['gpu']]
        
        stats = {}
        
        if cpu_values:
            stats['cpu'] = {
                'min': min(cpu_values),
                'max': max(cpu_values),
                'avg': sum(cpu_values) / len(cpu_values),
                'samples': len(cpu_values)
            }
        
        if mem_values:
            stats['memory'] = {
                'min': min(mem_values),
                'max': max(mem_values),
                'avg': sum(mem_values) / len(mem_values),
                'samples': len(mem_values)
            }
        
        if thread_values:
            stats['threads'] = {
                'min': min(thread_values),
                'max': max(thread_values),
                'avg': sum(thread_values) / len(thread_values),
                'samples': len(thread_values)
            }
        
        if gpu_values:
            stats['gpu'] = {
                'min': min(gpu_values),
                'max': max(gpu_values),
                'avg': sum(gpu_values) / len(gpu_values),
                'samples': len(gpu_values)
            }
        
        return stats
    
    def save_results(self):
        """儲存結果"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 儲存原始數據
        raw_file = self.output_dir / f"performance_raw_{timestamp}.json"
        with open(raw_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        
        # 計算並儲存統計數據
        stats = {
            "phase1_idle": self.calculate_stats(self.results['phase1_idle']),
            "phase2_connected": self.calculate_stats(self.results['phase2_connected']),
            "phase3_camera": self.calculate_stats(self.results['phase3_camera'])
        }
        
        stats_file = self.output_dir / f"performance_stats_{timestamp}.json"
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        
        # 生成報告
        report_file = self.output_dir / f"performance_report_{timestamp}.md"
        self.generate_report(stats, report_file)
        
        print(f"\n{'='*60}")
        print(f"💾 結果已儲存：")
        print(f"   原始數據: {raw_file}")
        print(f"   統計數據: {stats_file}")
        print(f"   分析報告: {report_file}")
        print(f"{'='*60}")
    
    def generate_report(self, stats, output_file):
        """生成分析報告"""
        report = []
        report.append("# EMG Monitor 效能分析報告\n")
        report.append(f"生成時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        report.append("---\n\n")
        
        phases = [
            ("phase1_idle", "階段一：未連接（僅 UI）"),
            ("phase2_connected", "階段二：已連接（接收 EMG）"),
            ("phase3_camera", "階段三：攝影機運作")
        ]
        
        for phase_key, phase_name in phases:
            report.append(f"## {phase_name}\n\n")
            
            if stats[phase_key]:
                s = stats[phase_key]
                
                if 'cpu' in s:
                    report.append(f"### 🔥 CPU 使用率\n")
                    report.append(f"- 最小值：{s['cpu']['min']:.1f}%\n")
                    report.append(f"- 最大值：{s['cpu']['max']:.1f}%\n")
                    report.append(f"- 平均值：{s['cpu']['avg']:.1f}%\n\n")
                
                if 'memory' in s:
                    report.append(f"### 💾 記憶體使用\n")
                    report.append(f"- 最小值：{s['memory']['min']:.1f} MB\n")
                    report.append(f"- 最大值：{s['memory']['max']:.1f} MB\n")
                    report.append(f"- 平均值：{s['memory']['avg']:.1f} MB\n\n")
                
                if 'threads' in s:
                    report.append(f"### 🧵 線程數量\n")
                    report.append(f"- 最小值：{int(s['threads']['min'])}\n")
                    report.append(f"- 最大值：{int(s['threads']['max'])}\n")
                    report.append(f"- 平均值：{s['threads']['avg']:.1f}\n\n")
                
                if 'gpu' in s:
                    report.append(f"### 🎮 GPU 使用率\n")
                    report.append(f"- 最小值：{s['gpu']['min']:.1f}%\n")
                    report.append(f"- 最大值：{s['gpu']['max']:.1f}%\n")
                    report.append(f"- 平均值：{s['gpu']['avg']:.1f}%\n\n")
            else:
                report.append("無數據\n\n")
            
            report.append("---\n\n")
        
        # 比較分析
        report.append("## 📈 階段比較\n\n")
        
        if all(stats[p] for p in ['phase1_idle', 'phase2_connected', 'phase3_camera']):
            report.append("| 指標 | 未連接 | 已連接 | 攝影機 | 增幅 |\n")
            report.append("|------|--------|--------|--------|------|\n")
            
            # CPU
            if all('cpu' in stats[p] for p in ['phase1_idle', 'phase2_connected', 'phase3_camera']):
                idle_cpu = stats['phase1_idle']['cpu']['avg']
                conn_cpu = stats['phase2_connected']['cpu']['avg']
                cam_cpu = stats['phase3_camera']['cpu']['avg']
                increase = ((cam_cpu - idle_cpu) / idle_cpu * 100) if idle_cpu > 0 else 0
                report.append(f"| CPU (%) | {idle_cpu:.1f} | {conn_cpu:.1f} | {cam_cpu:.1f} | +{increase:.0f}% |\n")
            
            # 記憶體
            if all('memory' in stats[p] for p in ['phase1_idle', 'phase2_connected', 'phase3_camera']):
                idle_mem = stats['phase1_idle']['memory']['avg']
                conn_mem = stats['phase2_connected']['memory']['avg']
                cam_mem = stats['phase3_camera']['memory']['avg']
                increase = ((cam_mem - idle_mem) / idle_mem * 100) if idle_mem > 0 else 0
                report.append(f"| 記憶體 (MB) | {idle_mem:.0f} | {conn_mem:.0f} | {cam_mem:.0f} | +{increase:.0f}% |\n")
            
            # GPU
            if all('gpu' in stats[p] for p in ['phase1_idle', 'phase2_connected', 'phase3_camera']):
                idle_gpu = stats['phase1_idle']['gpu']['avg']
                conn_gpu = stats['phase2_connected']['gpu']['avg']
                cam_gpu = stats['phase3_camera']['gpu']['avg']
                increase = cam_gpu - idle_gpu
                report.append(f"| GPU (%) | {idle_gpu:.1f} | {conn_gpu:.1f} | {cam_gpu:.1f} | +{increase:.1f}% |\n")
        
        report.append("\n---\n\n")
        report.append("## 🎯 優化建議\n\n")
        report.append("根據以上數據分析，建議關注以下方面：\n\n")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(''.join(report))


def main():
    profiler = PerformanceProfiler()
    
    print("""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║        EMG Monitor 效能分析工具                           ║
║                                                           ║
║  此工具將記錄三個階段的效能數據：                          ║
║  1. 未連接（僅 UI）                                       ║
║  2. 已連接（接收 EMG 資料）                               ║
║  3. 開啟攝影機（完整運作）                                ║
║                                                           ║
║  ⚠️  注意：需要 sudo 權限才能監控 GPU                      ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
""")
    
    input("\n請先啟動程式（python main.py），啟動後按 Enter 繼續...")
    
    # 階段一：未連接
    input("\n【階段一】程式應處於「未連接」狀態，按 Enter 開始監控（15秒）...")
    if not profiler.monitor_phase("階段一：未連接", "phase1_idle", duration=15, interval=2):
        print("❌ 監控失敗")
        return
    
    # 階段二：已連接
    input("\n【階段二】請連接 EMG 裝置，等待資料穩定後按 Enter 開始監控（15秒）...")
    if not profiler.monitor_phase("階段二：已連接", "phase2_connected", duration=15, interval=2):
        print("❌ 監控失敗")
        return
    
    # 階段三：攝影機
    input("\n【階段三】請開啟攝影機，等待預覽視窗出現後按 Enter 開始監控（15秒）...")
    if not profiler.monitor_phase("階段三：攝影機", "phase3_camera", duration=15, interval=2):
        print("❌ 監控失敗")
        return
    
    # 儲存結果
    profiler.save_results()
    
    print("\n✅ 效能分析完成！")
    print("\n下一步：")
    print("1. 查看 performance_logs/ 目錄中的報告")
    print("2. 根據數據找出效能瓶頸")
    print("3. 針對性優化程式碼")


if __name__ == "__main__":
    main()
