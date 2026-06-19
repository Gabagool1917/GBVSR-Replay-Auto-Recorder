"""Entry point for GBVSR Auto Recorder.

Run this with ``python main.py`` during development. When packaged with
PyInstaller (see build.spec), this becomes the script the .exe runs.
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from recorder.main_window import MainWindow
from recorder.theme import STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("GBVSR Auto Recorder")
    app.setOrganizationName("GBVSR Auto Recorder")
    app.setStyleSheet(STYLESHEET)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
