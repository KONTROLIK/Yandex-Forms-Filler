from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication

from core.model import Option, Question, ScaleRow
from core.types import QType
from ui.question_card import QuestionCard

APP = QApplication.instance() or QApplication([])


def make_question(qtype: str, **kwargs) -> Question:
    defaults = dict(qid=f"q_{qtype}", label=f"Вопрос {qtype}", type=qtype, index=1)
    defaults.update(kwargs)
    return Question(**defaults)


class EditorSmokeTest(unittest.TestCase):
    def test_all_editors(self) -> None:
        options = [Option(value="1", label="Первый"), Option(value="2", label="Второй")]
        rows = [ScaleRow(id="r1", label="Строка 1"), ScaleRow(id="r2", label="Строка 2")]
        columns = [Option(value="1", label="1"), Option(value="2", label="2")]
        child = make_question(QType.TEXT, qid="child", label="Имя")
        questions = [
            make_question(QType.TEXT),
            make_question(QType.LONG_TEXT),
            make_question(QType.NUMBER),
            make_question(QType.INTEGER),
            make_question(QType.EMAIL),
            make_question(QType.PHONE),
            make_question(QType.INN),
            make_question(QType.URL),
            make_question(QType.RADIO, options=options),
            make_question(QType.CHECKBOX, options=options, multiple=True),
            make_question(QType.DROPDOWN, options=options),
            make_question(QType.SUGGEST, options=options, filterable=True),
            make_question(QType.BOOLEAN, options=options),
            make_question(QType.DATE),
            make_question(QType.DATE_RANGE),
            make_question(QType.FILE),
            make_question(QType.MATRIX, rows=rows, columns=columns),
            make_question(QType.SERIES, children=[child]),
            make_question(QType.STATIC, label="Статичный текст", help="Описание"),
            make_question(QType.CAPTCHA),
            make_question(QType.PAYMENT, currency="₽"),
        ]
        for question in questions:
            card = QuestionCard(question)
            card.set_first()
            card.value()
            card.validate()
            card.deleteLater()

    def test_values(self) -> None:
        options = [Option(value="1", label="Первый"), Option(value="2", label="Второй")]
        radio = QuestionCard(make_question(QType.RADIO, options=options))
        radio.set_value("Второй")
        self.assertEqual(radio.value(), "Второй")
        check = QuestionCard(
            make_question(QType.CHECKBOX, options=options, multiple=True)
        )
        check.set_value(["Первый", "Второй"])
        self.assertEqual(check.value(), ["Первый", "Второй"])
        drop = QuestionCard(
            make_question(QType.DROPDOWN, options=options, filterable=True)
        )
        self.assertEqual(drop.editor.combo.count(), 2)
        drop.set_value("Второй")
        self.assertEqual(drop.value(), "Второй")
        number = QuestionCard(make_question(QType.INTEGER, min_value=1, max_value=10))
        number.set_value(5)
        self.assertEqual(number.value(), 5)
        boolean = QuestionCard(
            make_question(
                QType.BOOLEAN,
                options=[Option(value="1", label="Да"), Option(value="2", label="Нет")],
            )
        )
        boolean.set_value("Да")
        self.assertEqual(boolean.value(), "Да")
        single = QuestionCard(
            make_question(
                QType.BOOLEAN,
                options=[Option(value="1", label="Согласен")],
            )
        )
        single.set_value(True)
        self.assertIs(single.value(), True)
        matrix = QuestionCard(
            make_question(
                QType.MATRIX,
                rows=[ScaleRow(id="r1", label="Строка 1")],
                columns=options,
            )
        )
        matrix.set_value({"r1": "Второй"})
        self.assertEqual(matrix.value(), {"r1": "Второй"})


if __name__ == "__main__":
    unittest.main()
