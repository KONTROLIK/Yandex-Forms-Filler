from __future__ import annotations

from datetime import date
from typing import Any

from PySide6.QtCore import QDate, QRegularExpression, Qt, Signal
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from core.model import Question
from core.types import QType, normalize, option_matches, position_value


def _match_index(options, value: Any) -> int:
    if value is None or value == "":
        return -1
    position = position_value(value, len(options))
    if position is not None and position < len(options):
        return position
    text = str(value)
    for index, option in enumerate(options):
        if option_matches(option.label, option.value, text):
            return index
    return -1


class BaseEditor(QWidget):
    changed = Signal()

    def __init__(self, question: Question, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.question = question

    def get_value(self) -> Any:
        raise NotImplementedError

    def set_value(self, value: Any) -> None:
        raise NotImplementedError

    def clear(self) -> None:
        self.set_value(None)

    def set_first(self) -> None:
        pass

    def is_empty(self) -> bool:
        value = self.get_value()
        return value is None or value == "" or value == []


class TextEditor(BaseEditor):
    def __init__(self, question: Question, parent: QWidget | None = None) -> None:
        super().__init__(question, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(question.placeholder or "")
        max_length = question.extra.get("maxlength")
        if max_length:
            try:
                self.edit.setMaxLength(int(max_length))
            except (TypeError, ValueError):
                pass
        self.edit.textChanged.connect(lambda _: self.changed.emit())
        layout.addWidget(self.edit)

    def get_value(self) -> Any:
        text = self.edit.text()
        return text if text.strip() else None

    def set_value(self, value: Any) -> None:
        self.edit.setText("" if value is None else str(value))

    def clear(self) -> None:
        self.edit.clear()

    def set_first(self) -> None:
        pass


class LongTextEditor(BaseEditor):
    def __init__(self, question: Question, parent: QWidget | None = None) -> None:
        super().__init__(question, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QTextEdit()
        self.edit.setPlaceholderText(question.placeholder or "")
        self.edit.setFixedHeight(110)
        self.edit.textChanged.connect(self.changed.emit)
        layout.addWidget(self.edit)

    def get_value(self) -> Any:
        text = self.edit.toPlainText()
        return text if text.strip() else None

    def set_value(self, value: Any) -> None:
        self.edit.setPlainText("" if value is None else str(value))

    def clear(self) -> None:
        self.edit.clear()

    def set_first(self) -> None:
        pass


class NumberEditor(BaseEditor):
    def __init__(self, question: Question, parent: QWidget | None = None) -> None:
        super().__init__(question, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(
            "Целое число" if question.type == QType.INTEGER else "Число"
        )
        if question.type == QType.INTEGER:
            pattern = r"^-?\d*$"
        else:
            pattern = r"^-?\d*([.,]\d+)?$"
        self.edit.setValidator(
            QRegularExpressionValidator(QRegularExpression(pattern), self.edit)
        )
        self.edit.textChanged.connect(lambda _: self.changed.emit())
        layout.addWidget(self.edit)

    def get_value(self) -> Any:
        text = self.edit.text().strip().replace(",", ".")
        if not text or text in {"-", ".", "-."}:
            return None
        try:
            number = float(text)
        except ValueError:
            return text
        if self.question.type == QType.INTEGER:
            return int(number)
        return number

    def set_value(self, value: Any) -> None:
        self.edit.setText("" if value is None else str(value))

    def clear(self) -> None:
        self.edit.clear()

    def set_first(self) -> None:
        pass


class RadioEditor(BaseEditor):
    def __init__(self, question: Question, parent: QWidget | None = None) -> None:
        super().__init__(question, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.buttons: list[QRadioButton] = []
        self.group = None
        if not question.options:
            self.fallback = QLineEdit()
            self.fallback.setPlaceholderText("Введите вариант")
            self.fallback.textChanged.connect(lambda _: self.changed.emit())
            layout.addWidget(self.fallback)
            return
        self.fallback = None
        from PySide6.QtWidgets import QButtonGroup

        self.group = QButtonGroup(self)
        for option in question.options:
            button = QRadioButton(option.label)
            button.setEnabled(not option.disabled)
            self.group.addButton(button)
            self.buttons.append(button)
            layout.addWidget(button)
            button.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        if checked:
            self.changed.emit()

    def get_value(self) -> Any:
        if self.fallback is not None:
            text = self.fallback.text().strip()
            return text or None
        for button in self.buttons:
            if button.isChecked():
                return button.text()
        return None

    def set_value(self, value: Any) -> None:
        if self.fallback is not None:
            self.fallback.setText("" if value is None else str(value))
            return
        index = _match_index(self.question.options, value)
        for i, button in enumerate(self.buttons):
            button.setChecked(i == index)

    def clear(self) -> None:
        if self.fallback is not None:
            self.fallback.clear()
            return
        for button in self.buttons:
            button.setChecked(False)

    def set_first(self) -> None:
        if self.fallback is not None:
            return
        if self.buttons:
            self.buttons[0].setChecked(True)


class DropdownEditor(BaseEditor):
    def __init__(self, question: Question, parent: QWidget | None = None) -> None:
        super().__init__(question, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.combo = QComboBox()
        self.editable = bool(question.filterable or not question.options)
        self.combo.setEditable(self.editable)
        self.combo.setInsertPolicy(QComboBox.NoInsert)
        self.combo.setMaxVisibleItems(20)
        self.combo.setToolTip("Нажмите, чтобы открыть список, или начните вводить вариант")
        if self.editable:
            self.combo.setPlaceholderText("Начните вводить вариант")
            for option in question.options:
                self.combo.addItem(option.label, option.label)
            if question.options:
                completer = QCompleter([o.label for o in question.options], self)
                completer.setCaseSensitivity(Qt.CaseInsensitive)
                completer.setFilterMode(Qt.MatchContains)
                self.combo.setCompleter(completer)
            self.combo.setCurrentIndex(-1)
        else:
            self.combo.addItem("— не выбрано —", None)
            for option in question.options:
                self.combo.addItem(option.label, option.label)
        self.combo.currentIndexChanged.connect(lambda _: self.changed.emit())
        if self.editable:
            self.combo.editTextChanged.connect(lambda _: self.changed.emit())
        layout.addWidget(self.combo)

    def get_value(self) -> Any:
        if self.editable:
            text = self.combo.currentText().strip()
            return text or None
        data = self.combo.currentData()
        return data

    def set_value(self, value: Any) -> None:
        if self.editable:
            if value is None:
                self.combo.setCurrentIndex(-1)
            else:
                text = str(value)
                index = self.combo.findText(text, Qt.MatchFixedString)
                if index >= 0:
                    self.combo.setCurrentIndex(index)
                else:
                    self.combo.setEditText(text)
            return
        index = _match_index(self.question.options, value)
        self.combo.setCurrentIndex(index + 1 if index >= 0 else 0)

    def clear(self) -> None:
        if self.editable:
            self.combo.setCurrentIndex(-1)
        else:
            self.combo.setCurrentIndex(0)

    def set_first(self) -> None:
        if self.editable:
            if self.question.options:
                self.set_value(self.question.options[0].label)
            return
        if self.question.options:
            self.combo.setCurrentIndex(1)


class SuggestEditor(DropdownEditor):
    def __init__(self, question: Question, parent: QWidget | None = None) -> None:
        question.filterable = True
        super().__init__(question, parent)


class CheckboxEditor(BaseEditor):
    def __init__(self, question: Question, parent: QWidget | None = None) -> None:
        super().__init__(question, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.checkboxes: list[tuple[QCheckBox, Any]] = []
        self.other_edit: QLineEdit | None = None
        self.other_checkbox: QCheckBox | None = None
        for option in question.options:
            row = QHBoxLayout()
            checkbox = QCheckBox(option.label)
            checkbox.setEnabled(not option.disabled)
            checkbox.stateChanged.connect(lambda _: self.changed.emit())
            self.checkboxes.append((checkbox, option))
            row.addWidget(checkbox)
            if option.other:
                self.other_checkbox = checkbox
                self.other_edit = QLineEdit()
                self.other_edit.setPlaceholderText("Свой вариант")
                self.other_edit.textChanged.connect(lambda _: self.changed.emit())
                row.addWidget(self.other_edit, 1)
                self.other_edit.setVisible(False)
                checkbox.toggled.connect(self.other_edit.setVisible)
            row.addStretch(1)
            layout.addLayout(row)

    def get_value(self) -> Any:
        values = [option.label for checkbox, option in self.checkboxes if checkbox.isChecked()]
        if self.other_checkbox is not None and self.other_checkbox.isChecked():
            other = self.other_edit.text().strip() if self.other_edit else ""
            return {"values": values, "other": other}
        return values

    def set_value(self, value: Any) -> None:
        other = ""
        if isinstance(value, dict):
            other = str(value.get("other") or value.get("other_text") or "")
            value = value.get("values") or value.get("value") or []
        if isinstance(value, str):
            value = [value]
        values = value or []
        for checkbox, option in self.checkboxes:
            match = any(
                option_matches(option.label, option.value, str(item))
                for item in values
            )
            checkbox.setChecked(match)
        if self.other_checkbox is not None:
            if other:
                self.other_checkbox.setChecked(True)
                if self.other_edit:
                    self.other_edit.setText(other)
            elif self.other_edit:
                self.other_edit.clear()

    def clear(self) -> None:
        for checkbox, _ in self.checkboxes:
            checkbox.setChecked(False)
        if self.other_edit:
            self.other_edit.clear()

    def set_first(self) -> None:
        if self.checkboxes:
            self.checkboxes[0][0].setChecked(True)


class BooleanEditor(BaseEditor):
    def __init__(self, question: Question, parent: QWidget | None = None) -> None:
        super().__init__(question, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.combo: QComboBox | None = None
        self.checkbox: QCheckBox | None = None
        if len(question.options) >= 2:
            self.combo = QComboBox()
            self.combo.addItem("— не выбрано —", None)
            for option in question.options[:2]:
                self.combo.addItem(option.label or option.value, option.label or option.value)
            if self.combo.count() < 3:
                self.combo.addItem("Да", "Да")
                self.combo.addItem("Нет", "Нет")
            self.combo.currentIndexChanged.connect(lambda _: self.changed.emit())
            layout.addWidget(self.combo)
        else:
            label = question.options[0].label if question.options else "Да"
            self.checkbox = QCheckBox(label or "Да")
            self.checkbox.stateChanged.connect(lambda _: self.changed.emit())
            layout.addWidget(self.checkbox)

    def get_value(self) -> Any:
        if self.combo is not None:
            return self.combo.currentData()
        if self.checkbox is not None:
            return True if self.checkbox.isChecked() else None
        return None

    def set_value(self, value: Any) -> None:
        if self.combo is not None:
            if value is None:
                self.combo.setCurrentIndex(0)
                return
            index = self.combo.findData(value)
            if index < 0:
                for candidate in range(1, self.combo.count()):
                    data = self.combo.itemData(candidate)
                    if normalize(data) == normalize(value):
                        index = candidate
                        break
            if index < 0:
                truthy = value is True or normalize(value) in {"да", "true", "1", "yes"}
                index = 1 if truthy else 2
            self.combo.setCurrentIndex(index)
            return
        if self.checkbox is not None:
            self.checkbox.setChecked(bool(value))

    def clear(self) -> None:
        if self.combo is not None:
            self.combo.setCurrentIndex(0)
        elif self.checkbox is not None:
            self.checkbox.setChecked(False)

    def set_first(self) -> None:
        if self.combo is not None:
            self.combo.setCurrentIndex(1)
        elif self.checkbox is not None:
            self.checkbox.setChecked(True)


class DateEditor(BaseEditor):
    def __init__(self, question: Question, parent: QWidget | None = None) -> None:
        super().__init__(question, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edits: list[QLineEdit] = []
        if question.type == QType.DATE_RANGE:
            form = QFormLayout()
            for label in ("С", "По"):
                row = QHBoxLayout()
                edit = QLineEdit()
                edit.setPlaceholderText("ДД.ММ.ГГГГ")
                edit.textChanged.connect(lambda _: self.changed.emit())
                button = QToolButton()
                button.setText("…")
                button.clicked.connect(lambda _=False, e=edit: self._pick(e))
                row.addWidget(edit, 1)
                row.addWidget(button)
                self.edits.append(edit)
                form.addRow(label, row)
            layout.addLayout(form)
        else:
            row = QHBoxLayout()
            edit = QLineEdit()
            edit.setPlaceholderText("ДД.ММ.ГГГГ")
            edit.textChanged.connect(lambda _: self.changed.emit())
            button = QToolButton()
            button.setText("…")
            button.clicked.connect(lambda _=False, e=edit: self._pick(e))
            row.addWidget(edit, 1)
            row.addWidget(button)
            self.edits.append(edit)
            layout.addLayout(row)

    def _pick(self, edit: QLineEdit) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Выберите дату")
        layout = QVBoxLayout(dialog)
        calendar = QCalendarWidget(dialog)
        calendar.setSelectedDate(QDate.currentDate())
        layout.addWidget(calendar)
        buttons = QHBoxLayout()
        ok = QPushButton("Выбрать")
        cancel = QPushButton("Отмена")
        ok.clicked.connect(dialog.accept)
        cancel.clicked.connect(dialog.reject)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        if dialog.exec() == QDialog.Accepted:
            edit.setText(calendar.selectedDate().toString("dd.MM.yyyy"))

    def get_value(self) -> Any:
        values = [edit.text().strip() for edit in self.edits]
        if self.question.type == QType.DATE_RANGE:
            result = {}
            if values and values[0]:
                result["from"] = values[0]
            if len(values) > 1 and values[1]:
                result["to"] = values[1]
            return result or None
        return values[0] if values and values[0] else None

    def set_value(self, value: Any) -> None:
        if isinstance(value, dict):
            self.edits[0].setText(str(value.get("from") or ""))
            if len(self.edits) > 1:
                self.edits[1].setText(str(value.get("to") or ""))
            return
        self.edits[0].setText("" if value is None else str(value))

    def clear(self) -> None:
        for edit in self.edits:
            edit.clear()

    def set_first(self) -> None:
        pass


class FileEditor(BaseEditor):
    def __init__(self, question: Question, parent: QWidget | None = None) -> None:
        super().__init__(question, parent)
        self.paths: list[str] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.display = QLineEdit()
        self.display.setReadOnly(True)
        self.display.setPlaceholderText("Файл не выбран")
        browse = QPushButton("Обзор…")
        browse.clicked.connect(self._browse)
        clear = QPushButton("Очистить")
        clear.clicked.connect(self.clear)
        row.addWidget(self.display, 1)
        row.addWidget(browse)
        row.addWidget(clear)
        layout.addLayout(row)
        hint = QLabel(
            "Можно выбрать несколько файлов"
            if question.multiple
            else "Один файл"
        )
        hint.setStyleSheet("color: #777; font-size: 11px;")
        layout.addWidget(hint)

    def _browse(self) -> None:
        if self.question.multiple:
            paths, _ = QFileDialog.getOpenFileNames(self, "Выберите файлы")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Выберите файл")
            paths = [path] if path else []
        if paths:
            self.paths = paths
            self.display.setText("; ".join(paths))
            self.changed.emit()

    def get_value(self) -> Any:
        return list(self.paths) if self.paths else None

    def set_value(self, value: Any) -> None:
        if value is None or value == "":
            self.paths = []
        elif isinstance(value, (list, tuple)):
            self.paths = [str(p) for p in value]
        else:
            self.paths = [str(value)]
        self.display.setText("; ".join(self.paths))

    def clear(self) -> None:
        self.paths = []
        self.display.clear()
        self.changed.emit()

    def set_first(self) -> None:
        pass


class MatrixEditor(BaseEditor):
    def __init__(self, question: Question, parent: QWidget | None = None) -> None:
        super().__init__(question, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.combos: dict[str, QComboBox] = {}
        self.table = QTableWidget(len(question.rows), 2)
        self.table.setHorizontalHeaderLabels(["Параметр", "Оценка"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        for row_index, row in enumerate(question.rows):
            item = QTableWidgetItem(row.label)
            self.table.setItem(row_index, 0, item)
            combo = QComboBox()
            combo.addItem("—", None)
            for column in question.columns:
                combo.addItem(column.label, column.label)
            combo.currentIndexChanged.connect(lambda _: self.changed.emit())
            self.table.setCellWidget(row_index, 1, combo)
            self.combos[row.id or row.label] = combo
        layout.addWidget(self.table)
        if question.columns:
            row = QHBoxLayout()
            row.addWidget(QLabel("Заполнить все:"))
            self.bulk = QComboBox()
            for column in question.columns:
                self.bulk.addItem(column.label, column.label)
            row.addWidget(self.bulk, 1)
            button = QPushButton("Применить")
            button.clicked.connect(self._apply_bulk)
            row.addWidget(button)
            layout.addLayout(row)
        else:
            self.bulk = None

    def _apply_bulk(self) -> None:
        if self.bulk is None:
            return
        value = self.bulk.currentData()
        for combo in self.combos.values():
            index = combo.findData(value)
            if index >= 0:
                combo.setCurrentIndex(index)

    def get_value(self) -> Any:
        result = {}
        for key, combo in self.combos.items():
            value = combo.currentData()
            if value not in (None, ""):
                result[key] = value
        return result or None

    def set_value(self, value: Any) -> None:
        if not isinstance(value, dict):
            value = {}
        for key, combo in self.combos.items():
            index = combo.findData(value.get(key))
            if index < 0:
                for label, candidate in value.items():
                    if normalize(label) == normalize(key):
                        index = combo.findData(candidate)
                        break
            combo.setCurrentIndex(index if index >= 0 else 0)

    def clear(self) -> None:
        for combo in self.combos.values():
            combo.setCurrentIndex(0)

    def set_first(self) -> None:
        if not self.question.columns:
            return
        for combo in self.combos.values():
            if combo.count() > 1:
                combo.setCurrentIndex(1)


class SeriesEditor(BaseEditor):
    def __init__(self, question: Question, parent: QWidget | None = None) -> None:
        super().__init__(question, parent)
        self.instances: list[tuple[QGroupBox, dict[str, BaseEditor]]] = []
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.container = QVBoxLayout()
        self.layout.addLayout(self.container)
        add = QPushButton("Добавить экземпляр")
        add.clicked.connect(lambda: self.add_instance())
        self.layout.addWidget(add)
        if question.required:
            self.add_instance()

    def add_instance(self, values: dict[str, Any] | None = None) -> None:
        values = values or {}
        group = QGroupBox(f"Экземпляр {len(self.instances) + 1}")
        group_layout = QVBoxLayout(group)
        editors: dict[str, BaseEditor] = {}
        for child in self.question.children:
            label = QLabel(child.label or child.qid)
            label.setWordWrap(True)
            label.setStyleSheet("font-weight: 600;")
            group_layout.addWidget(label)
            editor = create_editor(child)
            editor.set_value(values.get(child.qid, values.get(child.label)))
            editor.changed.connect(self.changed.emit)
            group_layout.addWidget(editor)
            editors[child.qid] = editor
        remove = QPushButton("Удалить экземпляр")
        remove.clicked.connect(lambda _=False, g=group: self.remove_instance(g))
        group_layout.addWidget(remove)
        self.container.addWidget(group)
        self.instances.append((group, editors))
        self.changed.emit()

    def remove_instance(self, group: QGroupBox) -> None:
        for index, (candidate, _) in enumerate(self.instances):
            if candidate is group:
                self.instances.pop(index)
                self.container.removeWidget(group)
                group.deleteLater()
                break
        for index, (candidate, _) in enumerate(self.instances, start=1):
            candidate.setTitle(f"Экземпляр {index}")
        self.changed.emit()

    def get_value(self) -> Any:
        result = []
        for _, editors in self.instances:
            result.append({qid: editor.get_value() for qid, editor in editors.items()})
        return result or None

    def set_value(self, value: Any) -> None:
        while self.instances:
            self.remove_instance(self.instances[-1][0])
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    self.add_instance(item)

    def clear(self) -> None:
        while self.instances:
            self.remove_instance(self.instances[-1][0])

    def set_first(self) -> None:
        if not self.instances:
            self.add_instance()
        for _, editors in self.instances:
            for editor in editors.values():
                editor.set_first()

    def is_empty(self) -> bool:
        return not self.instances


class StaticEditor(BaseEditor):
    def __init__(self, question: Question, parent: QWidget | None = None) -> None:
        super().__init__(question, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(question.help or question.label)
        label.setWordWrap(True)
        label.setTextFormat(Qt.RichText)
        layout.addWidget(label)

    def get_value(self) -> Any:
        return None

    def set_value(self, value: Any) -> None:
        pass

    def is_empty(self) -> bool:
        return True


class CaptchaEditor(BaseEditor):
    def __init__(self, question: Question, parent: QWidget | None = None) -> None:
        super().__init__(question, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(
            "Форма содержит капчу. Автоматическое заполнение остановится, "
            "потребуется ручное подтверждение в видимом браузере."
        )
        label.setWordWrap(True)
        label.setStyleSheet("color: #a15c00;")
        layout.addWidget(label)

    def get_value(self) -> Any:
        return None

    def set_value(self, value: Any) -> None:
        pass

    def is_empty(self) -> bool:
        return True


class PaymentEditor(BaseEditor):
    def __init__(self, question: Question, parent: QWidget | None = None) -> None:
        super().__init__(question, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Сумма")
        self.edit.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"^\d*([.,]\d{0,2})?$"), self.edit)
        )
        self.edit.textChanged.connect(lambda _: self.changed.emit())
        row.addWidget(self.edit, 1)
        if question.currency:
            row.addWidget(QLabel(question.currency))
        layout.addLayout(row)
        warning = QLabel("Оплату нужно завершить вручную в браузере.")
        warning.setStyleSheet("color: #777; font-size: 11px;")
        warning.setWordWrap(True)
        layout.addWidget(warning)

    def get_value(self) -> Any:
        text = self.edit.text().strip().replace(",", ".")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return text

    def set_value(self, value: Any) -> None:
        self.edit.setText("" if value is None else str(value))

    def clear(self) -> None:
        self.edit.clear()

    def set_first(self) -> None:
        pass


def create_editor(question: Question, parent: QWidget | None = None) -> BaseEditor:
    qtype = question.type
    if qtype in {QType.TEXT, QType.EMAIL, QType.PHONE, QType.INN, QType.URL}:
        return TextEditor(question, parent)
    if qtype == QType.LONG_TEXT:
        return LongTextEditor(question, parent)
    if qtype in {QType.NUMBER, QType.INTEGER}:
        return NumberEditor(question, parent)
    if qtype == QType.RADIO:
        return RadioEditor(question, parent)
    if qtype == QType.CHECKBOX:
        return CheckboxEditor(question, parent)
    if qtype == QType.DROPDOWN:
        return DropdownEditor(question, parent)
    if qtype == QType.SUGGEST:
        return SuggestEditor(question, parent)
    if qtype == QType.BOOLEAN:
        return BooleanEditor(question, parent)
    if qtype in {QType.DATE, QType.DATE_RANGE}:
        return DateEditor(question, parent)
    if qtype == QType.FILE:
        return FileEditor(question, parent)
    if qtype == QType.MATRIX:
        return MatrixEditor(question, parent)
    if qtype == QType.SERIES:
        return SeriesEditor(question, parent)
    if qtype == QType.PAYMENT:
        return PaymentEditor(question, parent)
    if qtype == QType.CAPTCHA:
        return CaptchaEditor(question, parent)
    return StaticEditor(question, parent)
