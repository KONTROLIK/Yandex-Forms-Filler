from __future__ import annotations

import traceback

from PySide6.QtCore import QThread, Signal

from core.detect import discover_form
from core.driver import make_driver, quit_driver


class DiscoverWorker(QThread):
    log = Signal(str)
    finished_ok = Signal(object, object)
    failed = Signal(str)

    def __init__(
        self,
        url: str,
        browser: str = "edge",
        headless: bool = True,
        timeout: int = 45,
        log_dir: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.url = url
        self.browser = browser
        self.headless = headless
        self.timeout = timeout
        self.log_dir = log_dir

    def run(self) -> None:
        driver = None
        profile = None
        try:
            self.log.emit("Запуск браузера…")
            driver, profile = make_driver(
                browser=self.browser,
                headless=self.headless,
                log=self.log.emit,
                log_dir=self.log_dir,
            )
            self.log.emit("Открываю форму…")
            questions, meta = discover_form(
                driver,
                self.url,
                log=self.log.emit,
                timeout=self.timeout,
            )
            if not questions:
                raise RuntimeError("Вопросы не найдены")
            self.log.emit(
                f"Найдено вопросов: {len(questions)}, страниц: {meta.get('pages', 1)}"
            )
            self.finished_ok.emit(questions, meta)
        except Exception as exc:
            self.failed.emit(
                f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"
            )
        finally:
            quit_driver(driver, profile)
