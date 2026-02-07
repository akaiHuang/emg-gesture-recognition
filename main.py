"""Entry point for the WL-EMG monitor application."""

from __future__ import annotations

import asyncio
import os
import sys
import platform

# macOS Metal 優化：設定 Qt 使用 Metal 渲染後端
if platform.system() == 'Darwin':  # macOS
    os.environ['QSG_RHI_BACKEND'] = 'metal'
    os.environ['QT_MAC_WANTS_LAYER'] = '1'  # 啟用 Core Animation layer
    print("🍎 macOS 檢測到：使用 Metal 渲染後端")

from PyQt6 import QtWidgets
import pyqtgraph as pg
import qasync

from emg_monitor.ui.main_window import MainWindow


def run() -> None:
    """Launch the Qt application."""
    # 不要在這裡設定 antialias，已在 main_window.py 設定
    app = QtWidgets.QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    window = MainWindow()
    window.show()
    with loop:
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    run()
