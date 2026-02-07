#!/usr/bin/env python3
"""測試序列埠是否有資料進來"""

import serial
import time
import sys

PORT = '/dev/cu.usbserial-0001'
BAUDRATES = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]

def test_baudrate(port, baudrate, timeout=5):
    """測試特定鮑率"""
    print(f"\n測試鮑率: {baudrate}")
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.0
        )
        
        print(f"✓ 序列埠已開啟")
        
        start_time = time.time()
        total_bytes = 0
        
        while time.time() - start_time < timeout:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                total_bytes += len(data)
                print(f"  收到 {len(data)} bytes: {data[:20].hex()}..." if len(data) > 20 else f"  收到 {len(data)} bytes: {data.hex()}")
            time.sleep(0.1)
        
        ser.close()
        
        if total_bytes > 0:
            print(f"✓ 成功！共收到 {total_bytes} bytes")
            return True
        else:
            print(f"✗ 沒有收到任何資料")
            return False
            
    except Exception as e:
        print(f"✗ 錯誤: {e}")
        return False

if __name__ == '__main__':
    print(f"測試序列埠: {PORT}")
    print("=" * 60)
    print("請確認：")
    print("1. USB 藍牙接收器已插入")
    print("2. EMG 腕帶已開啟")
    print("3. 腕帶已與接收器配對")
    print("=" * 60)
    
    input("按 Enter 開始測試...")
    
    for baudrate in BAUDRATES:
        if test_baudrate(PORT, baudrate, timeout=3):
            print(f"\n✓✓✓ 找到正確的鮑率: {baudrate} ✓✓✓")
            sys.exit(0)
    
    print("\n✗ 所有鮑率都沒有收到資料")
    print("\n可能的原因：")
    print("1. EMG 腕帶未開啟")
    print("2. 腕帶未與接收器配對")
    print("3. 接收器故障或不兼容")
    print("4. 需要特殊的初始化指令")
