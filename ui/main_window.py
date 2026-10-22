from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.driver import quit_driver
from core.model import Question, fingerprint
from core.profiles import (
    apply_profile,
    load_profile,
    profile_path_for,
    save_profile,
)
from core.types import QType, TYPE_LABELS
from core.validate import first_error_by_qid, validate_questions
from ui.question_card import QuestionCard
from ui.settings_dialog import SettingsDialog
from workers.discover_worker import DiscoverWorker
from workers.fill_worker import FillWorker

APP_DATA_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
    "YandexFormsFiller",
)
DEFAULT_URL = ""
DEFAULT_KEYS = os.path.join(APP_DATA_DIR, "keys.txt")
DEFAULT_LOGS = os.path.join(APP_DATA_DIR, "logs")
DEFAULT_PROFILES = os.path.join(APP_DATA_DIR, "profiles")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Yandex Forms Filler")
        self.resize(1320, 900)
        self.settings = QSettings("YaForms", "Filler")
        self.questions: list[Question] = []
        self.cards: dict[str, QuestionCard] = {}
        self.tree_items: dict[str, QTreeWidgetItem] = {}
        self.series_parent: dict[str, str] = {}
        self.meta: dict = {}
        self.current_url = ""
        self.pending_profile: dict | None = None
        self.scan_worker: DiscoverWorker | None = None
        self.fill_worker: FillWorker | None = None
        self.manual_driver = None
        self.manual_profile = None
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(900)
        self.autosave_timer.timeout.connect(self._autosave)
        self._settings = self._load_settings()
        self._build_ui()
        self._restore_url()
        self.log("Готово. Вставьте ссылку на Яндекс Форму и нажмите «Сканировать».")

    # ---------- settings ----------

    def _load_settings(self) -> dict:
        return {
            "browser": self.settings.value("browser", "edge"),
            "scan_headless": self.settings.value("scan_headless", True, type=bool),
            "timeout": int(self.settings.value("timeout", 45)),
            "logs_dir": self.settings.value("logs_dir", DEFAULT_LOGS),
            "profiles_dir": self.settings.value("profiles_dir", DEFAULT_PROFILES),
            "keys_file": self.settings.value("keys_file", DEFAULT_KEYS),
        }

    def _save_settings(self) -> None:
        if hasattr(self, "keys_edit"):
            self._settings["keys_file"] = (
                self.keys_edit.text().strip() or DEFAULT_KEYS
            )
        for key, value in self._settings.items():
            self.settings.setValue(key, value)
        self.settings.setValue("last_url", self.url_edit.text().strip())

    def _restore_url(self) -> None:
        last = self.settings.value("last_url", DEFAULT_URL)
        self.url_edit.setText(str(last or DEFAULT_URL))

    # ---------- UI ----------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("Ссылка:"))
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://forms.yandex.ru/u/…")
        url_row.addWidget(self.url_edit, 1)
        self.btn_scan = QPushButton("Сканировать")
        self.btn_scan.clicked.connect(self.scan)
        url_row.addWidget(self.btn_scan)
        self.btn_load = QPushButton("Загрузить профиль")
        self.btn_load.clicked.connect(self.load_profile_dialog)
        url_row.addWidget(self.btn_load)
        self.btn_save = QPushButton("Сохранить профиль")
        self.btn_save.clicked.connect(self.save_profile_dialog)
        url_row.addWidget(self.btn_save)
        self.btn_settings = QPushButton("Настройки")
        self.btn_settings.clicked.connect(self.open_settings)
        url_row.addWidget(self.btn_settings)
        layout.addLayout(url_row)

        action_row = QHBoxLayout()
        self.btn_first = QPushButton("Все первые")
        self.btn_first.clicked.connect(self.fill_first)
        self.btn_first.setEnabled(False)
        action_row.addWidget(self.btn_first)
        self.btn_validate = QPushButton("Проверить")
        self.btn_validate.clicked.connect(self.validate_all)
        self.btn_validate.setEnabled(False)
        action_row.addWidget(self.btn_validate)
        self.btn_fill = QPushButton("Заполнить")
        self.btn_fill.clicked.connect(self.fill_form)
        self.btn_fill.setEnabled(False)
        action_row.addWidget(self.btn_fill)
        self.btn_stop = QPushButton("Остановить")
        self.btn_stop.clicked.connect(self.stop_fill)
        self.btn_stop.setEnabled(False)
        action_row.addWidget(self.btn_stop)

        self.auto_submit = QCheckBox("Отправить автоматически")
        action_row.addWidget(self.auto_submit)
        self.visible_browser = QCheckBox("Показывать браузер")
        self.visible_browser.setChecked(True)
        action_row.addWidget(self.visible_browser)

        action_row.addWidget(QLabel("Прогонов:"))
        self.runs_spin = QSpinBox()
        self.runs_spin.setRange(1, 100)
        self.runs_spin.setValue(1)
        action_row.addWidget(self.runs_spin)
        action_row.addWidget(QLabel("Пауза:"))
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 600)
        self.delay_spin.setValue(20)
        self.delay_spin.setSuffix(" сек")
        action_row.addWidget(self.delay_spin)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        keys_row = QHBoxLayout()
        keys_row.addWidget(QLabel("Ключи:"))
        self.keys_edit = QLineEdit(self._settings["keys_file"])
        keys_row.addWidget(self.keys_edit, 1)
        keys_browse = QPushButton("…")
        keys_browse.setFixedWidth(32)
        keys_browse.clicked.connect(self.browse_keys)
        keys_row.addWidget(keys_browse)
        layout.addLayout(keys_row)

        main_splitter = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(300)
        self.tree.itemClicked.connect(self.on_tree_clicked)
        main_splitter.addWidget(self.tree)

        right = QSplitter(Qt.Vertical)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.cards_host = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch(1)
        self.scroll.setWidget(self.cards_host)
        right.addWidget(self.scroll)

        tabs = QTabWidget()
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(4000)
        self.log_view.setStyleSheet("font-family: Consolas, monospace; font-size: 12px;")
        tabs.addTab(self.log_view, "Лог")

        self.results = QTableWidget(0, 3)
        self.results.setHorizontalHeaderLabels(["Прогон", "Ключ", "Статус"])
        self.results.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.results.verticalHeader().setVisible(False)
        self.results.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tabs.addTab(self.results, "Результаты")
        right.addWidget(tabs)
        right.setSizes([600, 220])
        main_splitter.addWidget(right)
        main_splitter.setSizes([330, 990])
        layout.addWidget(main_splitter, 1)

        self.status_label = QLabel("Вопросов: 0 | Заполнено: 0")
        self.statusBar().addWidget(self.status_label)

    # ---------- logging ----------

    def log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{stamp}] {message}")

    # ---------- scan ----------

    def scan(self) -> None:
        if self.scan_worker is not None and self.scan_worker.isRunning():
            return
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "Ссылка", "Вставьте ссылку на форму.")
            return
        if not url.startswith(("http://", "https://")):
            QMessageBox.warning(self, "Ссылка", "Ссылка должна начинаться с http:// или https://")
            return
        self.current_url = url
        self._save_settings()
        self._clear_questions()
        self.btn_scan.setEnabled(False)
        self.btn_load.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.btn_first.setEnabled(False)
        self.btn_validate.setEnabled(False)
        self.btn_fill.setEnabled(False)
        self.status_label.setText("Сканирование…")
        self.log(f"Сканирую {url}")
        self.scan_worker = DiscoverWorker(
            url=url,
            browser=self._settings["browser"],
            headless=bool(self._settings["scan_headless"]),
            timeout=int(self._settings["timeout"]),
            log_dir=self._settings["logs_dir"],
            parent=self,
        )
        self.scan_worker.log.connect(self.log)
        self.scan_worker.finished_ok.connect(self.on_scan_finished)
        self.scan_worker.failed.connect(self.on_scan_failed)
        self.scan_worker.finished.connect(self.on_scan_thread_finished)
        self.scan_worker.start()

    def on_scan_finished(self, questions, meta) -> None:
        self.questions = list(questions)
        self.meta = dict(meta or {})
        self._build_question_ui()
        self.btn_first.setEnabled(True)
        self.btn_validate.setEnabled(True)
        self.btn_fill.setEnabled(True)
        self.log(
            f"Готово: {len(self.questions)} вопросов, "
            f"страниц: {self.meta.get('pages', 1)}"
        )
        if self.meta.get("captcha"):
            self.log(
                "В форме есть капча: при заполнении браузер останется открытым "
                "для ручного подтверждения."
            )
        if self.pending_profile is not None:
            self._apply_loaded_profile(self.pending_profile)
            self.pending_profile = None
        else:
            self._try_autosave_load()
        self.update_status()

    def on_scan_failed(self, error: str) -> None:
        self.log(error)
        self.status_label.setText("Ошибка сканирования")
        QMessageBox.critical(self, "Не удалось просканировать форму", error.splitlines()[0])

    def on_scan_thread_finished(self) -> None:
        self.btn_scan.setEnabled(True)
        self.btn_load.setEnabled(True)
        self.btn_save.setEnabled(True)
        self.scan_worker = None

    def _clear_questions(self) -> None:
        self.questions = []
        self.cards.clear()
        self.tree_items.clear()
        self.series_parent.clear()
        self.tree.clear()
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.cards_layout.addStretch(1)

    def _build_question_ui(self) -> None:
        pages = sorted({q.page for q in self.questions})
        page_items: dict[int, QTreeWidgetItem] = {}
        use_pages = len(pages) > 1
        if use_pages:
            for page in pages:
                page_item = QTreeWidgetItem([f"Страница {page}"])
                page_item.setExpanded(True)
                self.tree.addTopLevelItem(page_item)
                page_items[page] = page_item
        for question in self.questions:
            card = QuestionCard(question, self.cards_host)
            card.changed.connect(lambda qid=question.qid: self.on_card_changed(qid))
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
            self.cards[question.qid] = card
            text = f"{question.index}. [{TYPE_LABELS.get(question.type, question.type)}] {question.label}"
            item = QTreeWidgetItem([text])
            item.setData(0, Qt.UserRole, question.qid)
            item.setToolTip(0, question.help or question.label)
            if use_pages:
                page_items[question.page].addChild(item)
            else:
                self.tree.addTopLevelItem(item)
            self.tree_items[question.qid] = item
            item.setData(0, Qt.UserRole + 2, text)
            if question.children:
                for child in question.children:
                    child_item = QTreeWidgetItem(
                        [f"{child.index}. {child.label}"]
                    )
                    child_item.setData(0, Qt.UserRole, child.qid)
                    child_item.setData(0, Qt.UserRole + 1, question.qid)
                    item.addChild(child_item)
                    self.series_parent[child.qid] = question.qid
        self.tree.expandAll()

    def on_tree_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        qid = item.data(0, Qt.UserRole)
        parent_qid = item.data(0, Qt.UserRole + 1)
        card = self.cards.get(qid) or self.cards.get(parent_qid)
        if card is not None:
            self.scroll.ensureWidgetVisible(card, 0, 30)

    def on_card_changed(self, qid: str) -> None:
        self.update_status()
        self.autosave_timer.start()

    def update_status(self) -> None:
        total = 0
        answered = 0
        for qid, card in self.cards.items():
            if card.question.type in {QType.STATIC, QType.HINT}:
                continue
            total += 1
            if not card.editor.is_empty():
                answered += 1
            item = self.tree_items.get(qid)
            if item is not None:
                base = item.data(0, Qt.UserRole + 2) or item.text(0)
                item.setText(0, ("✓ " if not card.editor.is_empty() else "") + str(base))
        self.status_label.setText(f"Вопросов: {total} | Заполнено: {answered}")

    # ---------- actions ----------

    def fill_first(self) -> None:
        for card in self.cards.values():
            if card.question.type in {QType.STATIC, QType.HINT}:
                continue
            card.set_first()
        self.update_status()
        self.log("Проставлены первые варианты. Проверьте ответы перед отправкой.")

    def validate_all(self) -> bool:
        for card in self.cards.values():
            card.value()
        errors = validate_questions(self.questions)
        for card in self.cards.values():
            card.clear_error()
        by_qid = first_error_by_qid(errors)
        for qid, message in by_qid.items():
            card = self.cards.get(qid) or self.cards.get(self.series_parent.get(qid, ""))
            if card is not None:
                card.set_error(message)
        if errors:
            first = errors[0]
            card = self.cards.get(first.qid) or self.cards.get(
                self.series_parent.get(first.qid, "")
            )
            if card is not None:
                self.scroll.ensureWidgetVisible(card, 0, 30)
            text = "\n".join(f"• {e.message}" for e in errors[:8])
            if len(errors) > 8:
                text += f"\n… и ещё {len(errors) - 8}"
            QMessageBox.warning(self, "Проверьте ответы", text)
            self.log(f"Найдено ошибок: {len(errors)}")
            return False
        self.log("Проверка пройдена: ошибок нет.")
        return True

    def _close_manual_browser(self) -> None:
        if self.manual_driver is None:
            return
        quit_driver(self.manual_driver, self.manual_profile)
        self.manual_driver = None
        self.manual_profile = None
        self.log("Предыдущий ручной браузер закрыт.")

    def fill_form(self) -> None:
        if not self.questions:
            QMessageBox.warning(self, "Нет вопросов", "Сначала просканируйте форму.")
            return
        if self.fill_worker is not None and self.fill_worker.isRunning():
            return
        if not self.validate_all():
            return
        auto = self.auto_submit.isChecked()
        runs = self.runs_spin.value()
        if runs > 1 and not auto:
            QMessageBox.information(
                self,
                "Пакетный режим",
                "Для нескольких прогонов включите «Отправить автоматически»: "
                "иначе пришлось бы вручную отправлять каждый браузер.",
            )
            return
        visible = self.visible_browser.isChecked() or not auto
        if not auto and not self.visible_browser.isChecked():
            self.visible_browser.setChecked(True)
        if runs > 1:
            answer = QMessageBox.question(
                self,
                "Подтверждение",
                f"Будет выполнено {runs} последовательных отправок формы. Продолжить?",
            )
            if answer != QMessageBox.Yes:
                return
        for card in self.cards.values():
            card.value()
        self._close_manual_browser()
        self.btn_scan.setEnabled(False)
        self.btn_first.setEnabled(False)
        self.btn_validate.setEnabled(False)
        self.btn_fill.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.log(
            f"Запускаю заполнение: прогонов {runs}, "
            f"автоотправка {'вкл' if auto else 'выкл'}"
        )
        self.fill_worker = FillWorker(
            url=self.current_url or self.url_edit.text().strip(),
            questions=self.questions,
            browser=self._settings["browser"],
            headless=not visible,
            submit=auto,
            runs=runs,
            delay=self.delay_spin.value(),
            timeout=int(self._settings["timeout"]),
            log_dir=self._settings["logs_dir"],
            parent=self,
        )
        self.fill_worker.log.connect(self.log)
        self.fill_worker.run_finished.connect(self.on_run_finished)
        self.fill_worker.finished_ok.connect(self.on_fill_finished)
        self.fill_worker.failed.connect(self.on_fill_failed)
        self.fill_worker.finished.connect(self.on_fill_thread_finished)
        self.fill_worker.start()

    def stop_fill(self) -> None:
        if self.fill_worker is not None and self.fill_worker.isRunning():
            self.fill_worker.cancel()
            self.log("Запрошена остановка…")

    def on_run_finished(self, index: int, akey, error) -> None:
        row = self.results.rowCount()
        self.results.insertRow(row)
        self.results.setItem(row, 0, QTableWidgetItem(str(index)))
        self.results.setItem(row, 1, QTableWidgetItem(str(akey or "")))
        status = "OK" if error is None else str(error)
        self.results.setItem(row, 2, QTableWidgetItem(status))
        if akey:
            self._append_key(str(akey))
        if error:
            self.log(f"Прогон {index}: ошибка: {error}")

    def on_fill_finished(self) -> None:
        self.log("Заполнение завершено.")
        self.btn_stop.setEnabled(False)
        self.status_label.setText("Заполнение завершено")

    def on_fill_failed(self, message: str) -> None:
        self.log(f"Ошибка заполнения: {message}")
        QMessageBox.critical(self, "Ошибка заполнения", message)

    def on_fill_thread_finished(self) -> None:
        worker = self.fill_worker
        if worker is not None:
            self.manual_driver = getattr(worker, "_manual_driver", None)
            self.manual_profile = getattr(worker, "_manual_profile", None)
        self.btn_scan.setEnabled(True)
        self.btn_first.setEnabled(True)
        self.btn_validate.setEnabled(True)
        self.btn_fill.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.fill_worker = None

    def _append_key(self, akey: str) -> None:
        path = self.keys_edit.text().strip() or DEFAULT_KEYS
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(akey + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self.log(f"Ключ сохранён: {akey} → {path}")
        except OSError as exc:
            self.log(f"Не удалось сохранить ключ: {exc}")

    def browse_keys(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Файл ключей", self.keys_edit.text() or DEFAULT_KEYS
        )
        if path:
            self.keys_edit.setText(path)
            self._settings["keys_file"] = path
            self._save_settings()

    # ---------- profiles ----------

    def save_profile_dialog(self) -> None:
        if not self.questions:
            QMessageBox.warning(self, "Профиль", "Сначала просканируйте форму.")
            return
        for card in self.cards.values():
            card.value()
        os.makedirs(self._settings["profiles_dir"], exist_ok=True)
        default_name = os.path.join(
            self._settings["profiles_dir"],
            f"profile_{fingerprint(self.questions)}.json",
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить профиль", default_name, "JSON (*.json)"
        )
        if not path:
            return
        try:
            save_profile(path, self.current_url, self.questions, meta=self.meta)
            self.log(f"Профиль сохранён: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Профиль", f"Не удалось сохранить: {exc}")

    def load_profile_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Загрузить профиль", self._settings["profiles_dir"], "JSON (*.json)"
        )
        if not path:
            return
        try:
            profile = load_profile(path)
        except Exception as exc:
            QMessageBox.critical(self, "Профиль", f"Не удалось загрузить: {exc}")
            return
        if not self.questions:
            self.pending_profile = profile
            self.log("Профиль загружен. Он применится после сканирования формы.")
            return
        self._apply_loaded_profile(profile)

    def _apply_loaded_profile(self, profile: dict) -> None:
        applied = apply_profile(self.questions, profile)
        for qid, card in self.cards.items():
            card.clear_error()
            card.set_value(card.question.answer)
        self.update_status()
        self.log(f"Профиль применён: заполнено полей {applied}.")
        if profile.get("fingerprint") != fingerprint(self.questions):
            self.log(
                "Внимание: структура формы отличается от сохранённой. "
                "Проверьте ответы."
            )

    def _autosave(self) -> None:
        if not self.questions or not self.current_url:
            return
        path = profile_path_for(self._settings["profiles_dir"], self.current_url)
        try:
            for card in self.cards.values():
                card.value()
            save_profile(path, self.current_url, self.questions, meta=self.meta)
        except Exception:
            pass

    def _try_autosave_load(self) -> None:
        path = profile_path_for(self._settings["profiles_dir"], self.current_url)
        if not os.path.exists(path):
            return
        try:
            profile = load_profile(path)
        except Exception:
            return
        if profile.get("fingerprint") == fingerprint(self.questions):
            self._apply_loaded_profile(profile)
            self.log("Загружен автосохранённый черновик ответов.")

    # ---------- settings ----------

    def open_settings(self) -> None:
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec():
            self._settings.update(dialog.values())
            self.keys_edit.setText(self._settings["keys_file"])
            self._save_settings()
            self.log("Настройки сохранены.")

    # ---------- close ----------

    def closeEvent(self, event) -> None:
        if self.scan_worker is not None and self.scan_worker.isRunning():
            QMessageBox.information(
                self,
                "Сканирование",
                "Дождитесь завершения сканирования формы, затем закройте приложение.",
            )
            event.ignore()
            return
        if self.fill_worker is not None and self.fill_worker.isRunning():
            answer = QMessageBox.question(
                self,
                "Закрыть приложение?",
                "Заполнение ещё выполняется. Остановить его и закрыть?",
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.fill_worker.cancel()
            if not self.fill_worker.wait(20000):
                QMessageBox.warning(
                    self,
                    "Заполнение",
                    "Операция ещё не остановилась. Попробуйте закрыть окно позже.",
                )
                event.ignore()
                return
        self._close_manual_browser()
        self._save_settings()
        event.accept()
