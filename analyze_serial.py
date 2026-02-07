#!/usr/bin/env python3
"""分析序列埠資料以找出封包格式"""

import serial
import time

PORT = '/dev/cu.usbserial-0001'
BAUDRATE = 9600

def analyze_data(duration=5):
    """收集並分析資料"""
    print(f"開始收集資料 {duration} 秒...")
    
    ser = serial.Serial(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=1.0
    )
    
    buffer = bytearray()
    start_time = time.time()
    
    while time.time() - start_time < duration:
        if ser.in_waiting > 0:
            data = ser.read(ser.in_waiting)
            buffer.extend(data)
        time.sleep(0.1)
    
    ser.close()
    
    print(f"\n收集到 {len(buffer)} bytes")
    print("\n前 200 bytes (hex):")
    print(' '.join(f'{b:02x}' for b in buffer[:200]))
    
    print("\n\n尋找重複模式...")
    
    # 尋找可能的標頭（3-byte 重複模式）
    header_candidates = {}
    for i in range(len(buffer) - 28):
        pattern = bytes(buffer[i:i+3])
        if pattern not in header_candidates:
            header_candidates[pattern] = []
        header_candidates[pattern].append(i)
    
    # 找出出現次數最多且間隔約 29 bytes 的模式
    print("\n最常見的 3-byte 模式（可能是標頭）：")
    sorted_patterns = sorted(header_candidates.items(), key=lambda x: len(x[1]), reverse=True)
    
    for pattern, positions in sorted_patterns[:10]:
        if len(positions) < 3:
            continue
        
        # 計算平均間隔
        intervals = [positions[i+1] - positions[i] for i in range(len(positions)-1)]
        avg_interval = sum(intervals) / len(intervals) if intervals else 0
        
        print(f"  {pattern.hex()} - 出現 {len(positions)} 次, 平均間隔 {avg_interval:.1f} bytes")
        
        if 25 <= avg_interval <= 35:  # 接近 29 bytes
            print(f"    ⭐ 可能是標頭！位置: {positions[:5]}")
            
            # 顯示第一個完整封包
            if positions[0] + 29 <= len(buffer):
                packet = buffer[positions[0]:positions[0]+29]
                print(f"    第一個封包 (29 bytes): {packet.hex()}")
                print(f"    封包類型 (byte 3): 0x{packet[3]:02x}")

if __name__ == '__main__':
    analyze_data(5)
