"""Serial port device manager for USB Bluetooth receiver communication."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

import serial
import serial.tools.list_ports

from . import data_parser

logger = logging.getLogger(__name__)


PacketCallback = Callable[[data_parser.EmgSample | data_parser.ImuSample], None]
StatusCallback = Callable[[str], None]


@dataclass
class SerialDeviceManager:
    """Manage serial port communication with USB Bluetooth receiver."""

    on_packet: PacketCallback
    on_status: StatusCallback = lambda msg: None
    baud_rate: int = 921600  # WL-EMG 使用 921600 鮑率（根據官方文檔）

    _serial: Optional[serial.Serial] = field(init=False, default=None)
    _listen_task: Optional[asyncio.Task[None]] = field(init=False, default=None)
    _running: bool = field(init=False, default=False)

    @staticmethod
    def list_ports() -> list[str]:
        """列出所有可用的序列埠"""
        ports = serial.tools.list_ports.comports()
        # 在 macOS 上，優先使用 cu.* 而非 tty.*
        serial_ports = []
        for port in ports:
            # 優先顯示 /dev/cu.* 版本
            if port.device.startswith('/dev/tty.'):
                cu_version = port.device.replace('/dev/tty.', '/dev/cu.')
                serial_ports.append(cu_version)
            else:
                serial_ports.append(port.device)
        
        # 過濾掉藍牙和內建埠，只保留 USB 序列埠
        usb_ports = [
            p for p in serial_ports 
            if 'usb' in p.lower() and 'bluetooth' not in p.lower()
        ]
        return usb_ports

    async def connect(self, port: str) -> None:
        """連接到指定的序列埠"""
        self.on_status(f"正在連接序列埠 {port}...")
        
        try:
            # 開啟序列埠
            self._serial = serial.Serial(
                port=port,
                baudrate=self.baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1.0
            )
            
            if not self._serial.is_open:
                raise RuntimeError(f"無法開啟序列埠 {port}")
            
            self.on_status(f"已連接到 {port}")
            
            # 啟動監聽任務
            self._running = True
            self._listen_task = asyncio.create_task(self._read_loop())
            
        except serial.SerialException as e:
            raise RuntimeError(f"序列埠連接失敗: {e}")

    async def disconnect(self) -> None:
        """斷開序列埠連接"""
        self._running = False
        
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None
        
        if self._serial and self._serial.is_open:
            self._serial.close()
            self._serial = None
        
        self.on_status("已斷開連接")

    async def _read_loop(self) -> None:
        """持續讀取序列埠資料"""
        buffer = bytearray()
        PACKET_LENGTH = 29  # 根據 data_parser.py 的 PAYLOAD_LENGTH
        EXPECTED_HEADER = b'\xd2\xd2\xd2'  # data_parser.py 中定義的標頭
        bytes_received = 0
        last_log_time = 0
        packets_found = 0
        
        self.on_status("等待資料中...")
        logger.info("開始監聽序列埠資料...")
        logger.info(f"尋找標頭: {EXPECTED_HEADER.hex()}")
        
        while self._running and self._serial and self._serial.is_open:
            try:
                # 非阻塞讀取
                if self._serial.in_waiting > 0:
                    data = self._serial.read(self._serial.in_waiting)
                    bytes_received += len(data)
                    buffer.extend(data)
                    
                    # 每秒記錄一次接收狀態
                    import time
                    current_time = time.time()
                    if current_time - last_log_time > 1.0:
                        logger.info(f"已接收 {bytes_received} bytes, 緩衝區: {len(buffer)} bytes, 已解析: {packets_found} 封包")
                        self.on_status(f"已接收 {bytes_received} bytes")
                        last_log_time = current_time
                    
                    # 除錯：顯示前 100 個位元組以尋找模式
                    if bytes_received <= 200:
                        logger.info(f"原始資料 ({len(data)} bytes): {data.hex()}")
                        # 搜尋可能的標頭模式
                        if bytes_received == 200:
                            logger.info(f"前 200 bytes 完整資料: {buffer[:200].hex()}")
                            logger.info("分析資料模式中...")
                    
                    # 嘗試尋找封包標頭並解析
                    while len(buffer) >= PACKET_LENGTH:
                        # 尋找標頭位置
                        header_pos = buffer.find(EXPECTED_HEADER)
                        
                        if header_pos == -1:
                            # 沒找到標頭，清除舊資料（保留最後幾個位元組以防標頭跨越）
                            if len(buffer) > PACKET_LENGTH:
                                buffer = buffer[-(PACKET_LENGTH-1):]
                            break
                        
                        # 移除標頭前的垃圾資料
                        if header_pos > 0:
                            buffer = buffer[header_pos:]
                        
                        # 檢查是否有完整封包
                        if len(buffer) < PACKET_LENGTH:
                            break
                        
                        # 提取完整封包
                        packet_data = bytes(buffer[:PACKET_LENGTH])
                        buffer = buffer[PACKET_LENGTH:]
                        
                        try:
                            # 解析封包
                            packet = data_parser.parse_packet(packet_data)
                            self.on_packet(packet)
                            packets_found += 1
                        except data_parser.PacketError as e:
                            logger.warning(f"封包解析錯誤: {e}")
                            if packets_found == 0:
                                logger.warning(f"問題封包 hex: {packet_data.hex()}")
                            # 繼續處理下一個封包
                
                # 短暫休眠，避免 CPU 過度使用
                await asyncio.sleep(0.01)
                
            except serial.SerialException as e:
                logger.error(f"序列埠讀取錯誤: {e}")
                self.on_status(f"序列埠錯誤: {e}")
                break
            except Exception as e:
                logger.error(f"資料處理錯誤: {e}")
                # 繼續嘗試讀取

    @property
    def is_connected(self) -> bool:
        """檢查是否已連接"""
        return self._serial is not None and self._serial.is_open
