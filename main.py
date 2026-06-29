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

    from recorder.paths import icon_path
    from PySide6.QtGui import QIcon
    icon_file = icon_path()
    if icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
