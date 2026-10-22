from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.model import Option, Question, ScaleRow
from core.types import QType
from core.validate import validate_question, validate_questions


def q(qtype: str, **kwargs) -> Question:
    defaults = dict(qid=f"q_{qtype}", label="Вопрос", type=qtype, index=1)
    defaults.update(kwargs)
    return Question(**defaults)


class ValidationTest(unittest.TestCase):
    def test_required_text(self) -> None:
        question = q(QType.TEXT, required=True)
        self.assertTrue(validate_question(question, None))
        self.assertFalse(validate_question(question, "ok"))

    def test_integer_bounds(self) -> None:
        question = q(QType.INTEGER, min_value=2, max_value=5)
        self.assertTrue(validate_question(question, 1))
        self.assertTrue(validate_question(question, 6))
        self.assertFalse(validate_question(question, 3))

    def test_boolean_value(self) -> None:
        question = q(
            QType.BOOLEAN,
            required=True,
            options=[Option(value="", label="Да")],
        )
        self.assertFalse(validate_question(question, True))
        self.assertFalse(validate_question(question, False))
        self.assertTrue(validate_question(question, None))

    def test_radio(self) -> None:
        question = q(
            QType.RADIO,
            required=True,
            options=[Option(value="1", label="Да"), Option(value="2", label="Нет")],
        )
        self.assertTrue(validate_question(question, None))
        self.assertTrue(validate_question(question, "Может быть"))
        self.assertFalse(validate_question(question, "Да"))

    def test_checkbox_limits(self) -> None:
        question = q(
            QType.CHECKBOX,
            multiple=True,
            min_selected=1,
            max_selected=2,
            options=[
                Option(value="1", label="A"),
                Option(value="2", label="B"),
                Option(value="3", label="C"),
            ],
        )
        self.assertTrue(validate_question(question, []))
        self.assertTrue(validate_question(question, ["A", "B", "C"]))
        self.assertFalse(validate_question(question, ["A"]))

    def test_checkbox_other(self) -> None:
        question = q(
            QType.CHECKBOX,
            required=True,
            multiple=True,
            options=[Option(value="1", label="Другое", other=True)],
        )
        self.assertTrue(validate_question(question, {"values": [], "other": ""}))
        self.assertFalse(
            validate_question(question, {"values": ["Другое"], "other": "Свой вариант"})
        )

    def test_matrix(self) -> None:
        question = q(
            QType.MATRIX,
            required=True,
            rows=[ScaleRow(id="r1", label="Строка")],
            columns=[Option(value="1", label="1"), Option(value="2", label="2")],
        )
        self.assertTrue(validate_question(question, {}))
        self.assertTrue(validate_question(question, {"r1": "3"}))
        self.assertFalse(validate_question(question, {"r1": "2"}))

    def test_date_range(self) -> None:
        question = q(QType.DATE_RANGE, required=True)
        self.assertTrue(validate_question(question, {"from": "2026-01-01", "to": ""}))
        self.assertFalse(
            validate_question(question, {"from": "2026-01-01", "to": "2026-01-02"})
        )
        self.assertFalse(
            validate_question(question, {"from": "01.01.2026", "to": "02.01.2026"})
        )

    def test_date_formats(self) -> None:
        question = q(QType.DATE)
        self.assertFalse(validate_question(question, "2026-05-15"))
        self.assertFalse(validate_question(question, "15.05.2026"))
        self.assertTrue(validate_question(question, "32.05.2026"))

    def test_file(self) -> None:
        question = q(QType.FILE, required=True)
        self.assertTrue(validate_question(question, []))
        self.assertTrue(validate_question(question, ["missing-file.txt"]))
        self.assertFalse(validate_question(question, [__file__]))

    def test_series_child(self) -> None:
        child = q(QType.TEXT, qid="child", label="Имя", required=True)
        question = q(QType.SERIES, required=True, children=[child])
        self.assertTrue(validate_question(question, []))
        self.assertTrue(validate_question(question, [{"child": ""}]))

    def test_series_boolean_child(self) -> None:
        child = q(
            QType.BOOLEAN,
            qid="child",
            label="Согласен",
            options=[Option(value="", label="Да")],
        )
        question = q(QType.SERIES, children=[child])
        self.assertFalse(validate_question(question, [{"child": True}]))
        self.assertTrue(validate_question(question, [{"child": "Иван"}]))

    def test_validate_questions(self) -> None:
        questions = [q(QType.TEXT, qid="a", required=True), q(QType.TEXT, qid="b")]
        self.assertEqual(len(validate_questions(questions)), 1)


if __name__ == "__main__":
    unittest.main()
