from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.model import Option, Question, fingerprint
from core.profiles import (
    apply_profile,
    load_profile,
    profile_path_for,
    save_profile,
)
from core.types import QType


def make_questions() -> list[Question]:
    return [
        Question(
            qid="q1",
            label="Регион",
            type=QType.DROPDOWN,
            index=1,
            options=[Option(value="1", label="Область")],
        ),
        Question(
            qid="q2",
            label="Класс",
            type=QType.RADIO,
            index=2,
            options=[Option(value="1", label="10"), Option(value="2", label="11")],
        ),
    ]


class ProfileTest(unittest.TestCase):
    def test_roundtrip(self) -> None:
        questions = make_questions()
        questions[0].answer = "Область"
        questions[1].answer = "10"
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "profile.json")
            save_profile(path, "https://example.test/form", questions)
            profile = load_profile(path)
            self.assertEqual(profile["url"], "https://example.test/form")
            self.assertEqual(
                profile["fingerprint"], fingerprint(questions)
            )
            fresh = make_questions()
            applied = apply_profile(fresh, profile)
            self.assertEqual(applied, 2)
            self.assertEqual(fresh[0].answer, "Область")
            self.assertEqual(fresh[1].answer, "10")

    def test_apply_by_label_when_qid_changed(self) -> None:
        questions = make_questions()
        questions[0].answer = "Область"
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "profile.json")
            save_profile(path, "https://example.test/form", questions)
            profile = load_profile(path)
            profile["labels"] = {"old_q1": "Регион", "old_q2": "Класс"}
            profile["answers"] = {"old_q1": "Область"}
            fresh = make_questions()
            apply_profile(fresh, profile)
            self.assertEqual(fresh[0].answer, "Область")

    def test_autosave_path(self) -> None:
        path = profile_path_for("profiles", "https://example.test/form")
        self.assertTrue(path.startswith("profiles"))
        self.assertTrue(path.endswith(".json"))
        self.assertIn("autosave_", path)

    def test_invalid_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"url": "x"}, handle)
            with self.assertRaises(ValueError):
                load_profile(path)


if __name__ == "__main__":
    unittest.main()
