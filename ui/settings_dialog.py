from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class PathRow(QWidget):
    def __init__(self, path: str = "", directory: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.directory = directory
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit(path)
        button = QPushButton("…")
        button.setFixedWidth(32)
        button.clicked.connect(self._browse)
        layout.addWidget(self.edit, 1)
        layout.addWidget(button)

    def _browse(self) -> None:
        if self.directory:
            path = QFileDialog.getExistingDirectory(
                self, "Выберите папку", self.edit.text()
            )
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Выберите файл", self.edit.text()
            )
        if path:
            self.edit.setText(path)

    def text(self) -> str:
        return self.edit.text().strip()


class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.browser = QComboBox()
        self.browser.addItem("Microsoft Edge", "edge")
        self.browser.addItem("Google Chrome", "chrome")
        index = self.browser.findData(settings.get("browser", "edge"))
        self.browser.setCurrentIndex(max(0, index))
        form.addRow("Браузер:", self.browser)

        self.scan_headless = QCheckBox("Сканировать форму без окна браузера")
        self.scan_headless.setChecked(bool(settings.get("scan_headless", True)))
        form.addRow("", self.scan_headless)

        self.timeout = QSpinBox()
        self.timeout.setRange(10, 180)
        self.timeout.setSuffix(" сек")
        self.timeout.setValue(int(settings.get("timeout", 45)))
        form.addRow("Таймаут:", self.timeout)

        self.logs_dir = PathRow(settings.get("logs_dir", ""), directory=True)
        form.addRow("Папка логов:", self.logs_dir)

        self.profiles_dir = PathRow(settings.get("profiles_dir", ""), directory=True)
        form.addRow("Папка профилей:", self.profiles_dir)

        self.keys_file = PathRow(settings.get("keys_file", ""), directory=False)
        form.addRow("Файл ключей:", self.keys_file)

        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "browser": self.browser.currentData(),
            "scan_headless": self.scan_headless.isChecked(),
            "timeout": self.timeout.value(),
            "logs_dir": self.logs_dir.text(),
            "profiles_dir": self.profiles_dir.text(),
            "keys_file": self.keys_file.text(),
        }
