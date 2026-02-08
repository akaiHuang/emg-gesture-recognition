# EMG Gesture Recognition

## About

EMG Gesture Recognition 是一套即時肌電（EMG）訊號擷取與手勢辨識系統，針對多通道生物訊號提供端到端處理流程。適合用於穿戴式互動、復健/運動監測與生物訊號驅動介面的研究與原型。

## 📋 Quick Summary

> 💪 **EMG Gesture Recognition** 是一套即時 8 通道肌電訊號（EMG）生物感測介面系統，專為肌肉活動監測與手勢辨識設計。📡 直接連接 WL-EMG 硬體設備，支援 USB 藍牙接收器與 BLE 自動偵測，以 200Hz 取樣率即時擷取 24-bit ADC 高精度訊號。📊 提供雙視圖顯示系統——全通道合併檢視與 8 個獨立示波器（2x4 網格），搭配 Metal/OpenGL GPU 加速渲染。✋ 整合 MediaPipe 21 關鍵點手部骨架追蹤，支援 9 種預設手勢辨識（握拳、張開、捏取、豎拇指等）。🎥 同步錄製 EMG 訊號 + 攝影機影像 + 手部骨架數據，完美時間對齊。⚡ 經過迭代效能優化，CPU 使用率降低 54%、記憶體降低 83%。🧠 採用 PyQt6、PyTorch、OpenCV 等技術棧，適合人機互動、穿戴式運算、神經介面研究領域的研究者與工程師！

**Real-time 8-Channel Biosignal Interface for Muscle Activity Monitoring and Hand Gesture Classification**

---

## 💡 Why This Exists

Most biosignal research tools are either locked behind expensive proprietary software or limited to offline batch analysis. This project bridges that gap -- a complete desktop application that connects directly to WL-EMG hardware, visualizes 8 channels of raw electromyography signals in real time, and classifies hand gestures using synchronized camera-based hand tracking. It is purpose-built for researchers and engineers working at the intersection of human-computer interaction, wearable computing, and neural interface design.

## 🏗️ Architecture

```
WL-EMG 8-Channel Hardware (EMG + 6-axis IMU)
        |
        | Serial / BLE @ 921600 baud, 200 Hz
        v
+-----------------------------------------------+
|  Data Acquisition Layer                        |
|  serial_device.py / ble.py --> data_parser.py  |
|       --> Ring Buffers (8ch EMG + IMU)         |
+-----------------------------------------------+
        |
        +---> Real-time 8-Channel Waveform Display (PyQtGraph, Metal-accelerated)
        |         - Combined all-channel view
        |         - 8 independent oscilloscopes (2x4 grid)
        |         - 5-level signal quality indicators
        |
        +---> Motion Recording System
        |         - Synchronized EMG + Camera + MediaPipe hand tracking
        |         - .npz data + .mp4 video with skeleton overlay
        |
        +---> Gesture Recognition Pipeline
                  - MediaPipe 21-point hand skeleton
                  - 9 preset gestures (fist, open, pinch, thumbs up, etc.)
                  - Performance profiling and benchmarking
```

### Key Capabilities

- **Hardware-connected**: Reads 8 channels of muscle signals via USB Bluetooth receiver or BLE with auto-detection
- **200 Hz real-time visualization**: Dual-view system (combined + individual oscilloscopes) with Metal/OpenGL GPU acceleration
- **5-level signal quality system**: Standby > Weak > Good > Strong > Optimal, with adaptive thresholds and hysteresis
- **Synchronized recording**: EMG signals + camera video + MediaPipe hand skeleton, perfectly time-aligned
- **Gesture recognition**: 9 preset hand gestures with MediaPipe 21-keypoint tracking
- **Performance optimized**: CPU reduced 54% and memory reduced 83% through iterative profiling (136.9% down to 62.5% CPU, 4147 MB down to 708 MB)

### Hardware Specifications

| Parameter | Value |
|---|---|
| Sample Rate | 200 Hz |
| EMG Channels | 8 (24-bit ADC) |
| IMU | 6-axis (3-axis gyro + 3-axis accelerometer, 16-bit) |
| Baud Rate | 921,600 |
| Packet Size | 29 bytes/packet |
| Display Refresh | 20 FPS |

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| UI Framework | PyQt6, PyQtGraph |
| Signal Processing | NumPy, SciPy, scikit-learn |
| Computer Vision | OpenCV, MediaPipe (21-point hand tracking) |
| Deep Learning | PyTorch |
| Hardware I/O | pyserial (921600 baud), bleak (BLE) |
| GPU Acceleration | Metal (macOS), OpenGL, PyOpenGL |
| Async Runtime | asyncio, qasync |

## 🏁 Quick Start

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install core dependencies
pip install -r requirements.txt

# Install gesture recognition dependencies (optional)
pip install -r requirements_gesture.txt

# Launch the EMG monitor
python main.py
```

### Hardware Setup

1. Connect the WL-EMG Bluetooth receiver via USB
2. Power on the EMG armband and ensure pairing
3. Select the serial port from the dropdown (macOS: `/dev/cu.usbserial-*`)
4. Click Connect -- system auto-calibrates in ~2.5 seconds

> See the included `WL-EMG.pdf` and `WL-EMG2.pdf` documentation for detailed hardware specifications.

## 📁 Project Structure

```
emg-gesture-recognition/
  main.py                        # Application entry point (Metal-optimized on macOS)
  emg_monitor/
    config.py                    # Central config (channels, sample rate, buffer)
    serial_device.py             # Serial port device manager (921600 baud)
    ble.py                       # BLE device communication
    data_parser.py               # Raw EMG/IMU packet parsing
    buffers.py                   # Ring buffer for signal data
    device_manager.py            # Unified device abstraction
    simulator.py                 # Signal simulator for hardware-free testing
    motion_recorder.py           # Synchronized EMG + camera recording
    ui/
      main_window.py             # PyQt6 main window with dual-view waveforms
  gesture_recognition_demo/      # MediaPipe gesture classification with profiling
  models/                        # Trained gesture recognition models
  recordings/                    # Saved EMG sessions (.npz + .mp4)
  screenshot/                    # Application screenshots
  performance_profiler.py        # System performance benchmarking
  docs/                          # Development documentation
```

## 📜 Version History

| Version | Focus |
|---|---|
| v1.0 | 8-channel monitoring with single combined view |
| v2.0 | Dual-view system (combined + 8 independent oscilloscopes) |
| v2.1 | 5-level signal quality with intuitive color mapping |
| v3.0 | IMU integration (archived -- too complex for core use case) |
| v3.1 | Gesture recognition + synchronized motion recording (current) |

---

**Disclaimer:** This system is intended for research and educational purposes only. Not for medical diagnosis.

Built by [Huang Akai (Kai)](https://github.com/akaihuang) -- Creative Technologist, Founder @ Universal FAW Lab