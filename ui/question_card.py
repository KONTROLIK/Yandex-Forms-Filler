from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.model import Question, ValidationError
from core.types import QType, TYPE_LABELS
from core.validate import validate_question
from .editors import create_editor


class QuestionCard(QFrame):
    changed = Signal()

    def __init__(self, question: Question, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.question = question
        self.setObjectName("QuestionCard")
        self.setStyleSheet(
            """
            QFrame#QuestionCard {
                background: #ffffff;
                border: 1px solid #e2e2e2;
                border-radius: 8px;
            }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        index = QLabel(f"{question.index}.")
        index.setStyleSheet("color: #888; font-weight: 600;")
        header.addWidget(index)

        label = QLabel(question.label or "Без названия")
        label.setWordWrap(True)
        label.setStyleSheet("font-weight: 600; font-size: 14px; color: #222;")
        header.addWidget(label, 1)

        if question.required:
            required = QLabel("*")
            required.setStyleSheet("color: #d33; font-weight: 700;")
            header.addWidget(required)

        badge = QLabel(TYPE_LABELS.get(question.type, question.type))
        badge.setStyleSheet(
            "background: #eef3ff; color: #3659a8; border-radius: 4px; "
            "padding: 2px 6px; font-size: 11px;"
        )
        header.addWidget(badge)
        layout.addLayout(header)

        if question.help and question.type != QType.STATIC:
            help_label = QLabel(question.help)
            help_label.setWordWrap(True)
            help_label.setStyleSheet("color: #777; font-size: 12px;")
            layout.addWidget(help_label)

        self.editor = create_editor(question, self)
        self.editor.changed.connect(self._on_changed)
        layout.addWidget(self.editor)

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #c62828; font-size: 12px;")
        self.error_label.hide()
        layout.addWidget(self.error_label)

        if question.answer is not None:
            self.editor.set_value(question.answer)

    def _on_changed(self) -> None:
        self.error_label.hide()
        self.changed.emit()

    def value(self) -> Any:
        value = self.editor.get_value()
        self.question.answer = value
        return value

    def set_value(self, value: Any) -> None:
        self.question.answer = value
        self.editor.set_value(value)

    def set_first(self) -> None:
        self.editor.set_first()
        self.question.answer = self.editor.get_value()
        self.changed.emit()

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()
        self.setStyleSheet(
            """
            QFrame#QuestionCard {
                background: #fffafa;
                border: 1px solid #e57373;
                border-radius: 8px;
            }
            """
        )

    def clear_error(self) -> None:
        self.error_label.hide()
        self.setStyleSheet(
            """
            QFrame#QuestionCard {
                background: #ffffff;
                border: 1px solid #e2e2e2;
                border-radius: 8px;
            }
            """
        )

    def validate(self) -> list[ValidationError]:
        self.value()
        errors = validate_question(self.question, self.question.answer)
        if errors:
            self.set_error(errors[0].message)
        else:
            self.clear_error()
        return errors
