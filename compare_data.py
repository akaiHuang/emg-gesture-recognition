#!/usr/bin/env python3
"""比較有無手環時的資料差異"""

import serial
import time
import sys

PORT = '/dev/cu.usbserial-0001'
BAUDRATE = 921600

def capture_data(duration=5, description=""):
    """捕獲指定時間的資料"""
    print(f"\n{'='*60}")
    print(f"開始捕獲資料: {description}")
    print(f"{'='*60}")
    
    try:
        ser = serial.Serial(port=PORT, baudrate=BAUDRATE, timeout=1.0)
        buffer = bytearray()
        start_time = time.time()
        
        while time.time() - start_time < duration:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                buffer.extend(data)
            time.sleep(0.01)
        
        ser.close()
        
        print(f"捕獲到 {len(buffer)} bytes")
        
        if len(buffer) > 0:
            # 顯示前 200 bytes
            print(f"\n前 200 bytes (hex):")
            hex_str = ' '.join(f'{b:02x}' for b in buffer[:200])
            for i in range(0, len(hex_str), 80):
                print(hex_str[i:i+80])
            
            # 尋找 D2 D2 D2 標頭
            header = b'\xd2\xd2\xd2'
            positions = []
            for i in range(len(buffer) - 2):
                if buffer[i:i+3] == header:
                    positions.append(i)
            
            print(f"\n找到 {len(positions)} 個 D2 D2 D2 標頭")
            if len(positions) > 0:
                print(f"標頭位置: {positions[:10]}")
                
                # 分析第一個封包
                if positions[0] + 29 <= len(buffer):
                    packet = buffer[positions[0]:positions[0]+29]
                    print(f"\n第一個封包 (29 bytes):")
                    print(' '.join(f'{b:02x}' for b in packet))
                    print(f"  標頭: {packet[0]:02x} {packet[1]:02x} {packet[2]:02x}")
                    print(f"  類型: 0x{packet[3]:02x} ({'AA=EMG' if packet[3]==0xAA else 'BB=IMU' if packet[3]==0xBB else '未知'})")
                    print(f"  序號: {packet[4]}")
                
                # 計算封包間隔
                if len(positions) > 1:
                    intervals = [positions[i+1] - positions[i] for i in range(min(10, len(positions)-1))]
                    avg_interval = sum(intervals) / len(intervals)
                    print(f"\n前10個封包間隔: {intervals}")
                    print(f"平均間隔: {avg_interval:.1f} bytes (預期: 29)")
            else:
                print("⚠️ 未找到任何 D2 D2 D2 標頭")
                print("這可能表示：")
                print("  1. 鮑率不正確")
                print("  2. 手環未連接或未配對")
                print("  3. 資料格式與預期不同")
        else:
            print("⚠️ 未接收到任何資料")
        
        return buffer
        
    except Exception as e:
        print(f"錯誤: {e}")
        return bytearray()

if __name__ == '__main__':
    print("WL-EMG 資料分析工具")
    print("=" * 60)
    
    # 測試 1: 無手環
    input("\n請確認：手環已拔掉或關閉，按 Enter 開始捕獲...")
    data_without = capture_data(5, "無手環")
    
    # 測試 2: 有手環
    input("\n\n請確認：手環已開啟並配對，按 Enter 開始捕獲...")
    data_with = capture_data(5, "有手環")
    
    # 比較
    print("\n" + "="*60)
    print("比較結果:")
    print("="*60)
    print(f"無手環: {len(data_without)} bytes")
    print(f"有手環: {len(data_with)} bytes")
    
    if len(data_with) > len(data_without):
        print("\n✓ 有手環時資料量更大（正常）")
    elif len(data_without) > 0:
        print("\n⚠️ 警告：無手環時仍有資料（可能是噪音或錯誤配置）")
