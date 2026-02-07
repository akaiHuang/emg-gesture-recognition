#!/usr/bin/env python3
"""測試：將原始資料直接顯示為波形"""

import serial
import time
import struct

PORT = '/dev/cu.usbserial-0001'
BAUDRATE = 9600

def read_and_display(duration=10):
    """讀取資料並嘗試解析為數值"""
    ser = serial.Serial(port=PORT, baudrate=BAUDRATE, timeout=1.0)
    
    print("開始讀取資料...")
    print("假設：每個 byte 代表一個 EMG 樣本值")
    
    start_time = time.time()
    sample_count = 0
    
    while time.time() - start_time < duration:
        if ser.in_waiting > 0:
            data = ser.read(ser.in_waiting)
            
            for byte in data:
                # 將 byte 轉換為有符號整數 (-128 to 127)
                signed_value = byte - 128 if byte > 127 else byte
                sample_count += 1
                
                if sample_count % 100 == 0:
                    print(f"樣本 {sample_count}: {signed_value} (原始: 0x{byte:02x})")
        
        time.sleep(0.01)
    
    ser.close()
    print(f"\n共收到 {sample_count} 個樣本")
    print(f"採樣率約: {sample_count / duration:.1f} Hz")

if __name__ == '__main__':
    read_and_display(5)
