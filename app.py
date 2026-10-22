from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow

APP_VERSION = "1.0.0"


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Yandex Forms Filler")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("YaForms")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
