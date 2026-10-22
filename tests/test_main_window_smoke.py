from __future__ import annotations

import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from core.model import Option, Question
from core.profiles import load_profile, profile_path_for
from core.types import QType

APP = QApplication.instance() or QApplication([])


class MainWindowSmokeTest(unittest.TestCase):
    def test_build_and_first(self) -> None:
        settings_dir = tempfile.mkdtemp(prefix="yaform-settings-")
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, settings_dir)
        from ui.main_window import MainWindow

        window = MainWindow()
        options = [Option(value="1", label="Первый"), Option(value="2", label="Второй")]
        window.questions = [
            Question(
                qid="q1",
                label="Один вариант",
                type=QType.RADIO,
                index=1,
                options=options,
                required=True,
            ),
            Question(
                qid="q2",
                label="Текст",
                type=QType.TEXT,
                index=2,
                required=True,
            ),
            Question(
                qid="q3",
                label="Инструкция",
                type=QType.STATIC,
                index=3,
            ),
        ]
        window.meta = {"pages": 1}
        window._build_question_ui()
        window.update_status()
        self.assertEqual(len(window.cards), 3)
        window.fill_first()
        self.assertEqual(window.cards["q1"].value(), "Первый")
        self.assertIsNone(window.cards["q2"].value())
        window._settings["profiles_dir"] = settings_dir
        window.current_url = "https://example.test/form"
        window._autosave()
        path = profile_path_for(settings_dir, window.current_url)
        self.assertTrue(os.path.exists(path))
        profile = load_profile(path)
        self.assertEqual(profile["answers"]["q1"], "Первый")
        window.close()
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
