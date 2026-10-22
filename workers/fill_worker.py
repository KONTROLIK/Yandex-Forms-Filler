from __future__ import annotations

import copy
import os
import time
import traceback
from datetime import datetime

from PySide6.QtCore import QThread, Signal

from core.driver import make_driver, open_url, quit_driver
from core.fill import CaptchaRequired, FormFiller


class FillWorker(QThread):
    log = Signal(str)
    run_finished = Signal(int, object, object)
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(
        self,
        url: str,
        questions,
        browser: str = "edge",
        headless: bool = False,
        submit: bool = True,
        runs: int = 1,
        delay: int = 20,
        timeout: int = 45,
        log_dir: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.url = url
        self.questions = questions
        self.browser = browser
        self.headless = headless
        self.submit = submit
        self.runs = max(1, int(runs))
        self.delay = max(0, int(delay))
        self.timeout = timeout
        self.log_dir = log_dir
        self._cancel = False
        self._log_file = None
        self._manual_driver = None
        self._manual_profile = None

    def cancel(self) -> None:
        self._cancel = True

    def _write_log(self, message: str) -> None:
        self.log.emit(message)
        if self._log_file is not None:
            try:
                stamp = datetime.now().strftime("%H:%M:%S")
                self._log_file.write(f"[{stamp}] {message}\n")
                self._log_file.flush()
            except Exception:
                pass

    def run(self) -> None:
        run_root = None
        if self.log_dir:
            run_root = os.path.join(
                self.log_dir, datetime.now().strftime("run_%Y%m%d_%H%M%S")
            )
            os.makedirs(run_root, exist_ok=True)
            self._log_file = open(
                os.path.join(run_root, "fill.log"), "w", encoding="utf-8"
            )

        had_error = False
        try:
            for index in range(1, self.runs + 1):
                if self._cancel:
                    self._write_log("Остановлено пользователем")
                    break
                self._write_log(f"--- Прогон {index} из {self.runs} ---")
                driver = None
                profile = None
                failed = False
                leave_open = False
                try:
                    driver, profile = make_driver(
                        browser=self.browser,
                        headless=self.headless,
                        log=self._write_log,
                        log_dir=run_root,
                    )
                    open_url(driver, self.url, log=self._write_log, timeout=self.timeout)
                    questions = copy.deepcopy(self.questions)
                    filler = FormFiller(
                        driver,
                        log=self._write_log,
                        timeout=self.timeout,
                        screenshot_dir=run_root,
                    )
                    result = filler.fill(questions, submit=self.submit)
                    akey = result.get("akey")
                    if self.submit:
                        if akey:
                            self._write_log(f"Ключ: {akey}")
                        else:
                            self._write_log(
                                "Форма отправлена, но akey не найден в URL"
                            )
                    else:
                        self._write_log("Форма заполнена. Браузер оставлен открытым.")
                    self.run_finished.emit(index, akey, None)
                except Exception as exc:
                    had_error = True
                    if isinstance(exc, CaptchaRequired):
                        leave_open = True
                    else:
                        failed = True
                    message = f"{type(exc).__name__}: {exc}"
                    self._write_log(message)
                    self._write_log(traceback.format_exc())
                    self.run_finished.emit(index, None, message)
                    self.failed.emit(message)
                    break
                finally:
                    if self._cancel or failed:
                        quit_driver(driver, profile)
                    elif leave_open or not self.submit:
                        self._manual_driver = driver
                        self._manual_profile = profile
                        if leave_open:
                            self._write_log(
                                "Капча: браузер оставлен открытым для ручного прохождения."
                            )
                        else:
                            self._write_log(
                                "Браузер не закрывается: проверьте ответы и отправьте вручную."
                            )
                    else:
                        quit_driver(driver, profile)
                if index < self.runs:
                    self._write_log(f"Пауза {self.delay} сек. перед следующим прогоном")
                    for _ in range(self.delay * 2):
                        if self._cancel:
                            break
                        time.sleep(0.5)
            if not self._cancel and not had_error:
                self.finished_ok.emit()
        finally:
            if self._log_file is not None:
                try:
                    self._log_file.close()
                except Exception:
                    pass
