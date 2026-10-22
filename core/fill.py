from __future__ import annotations

import os
import re
import time
from typing import Any, Callable, Iterable
from urllib.parse import parse_qs, urlparse

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    JavascriptException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from .detect import safe_text
from .model import Question
from .types import QType, normalize, option_matches, position_value

Log = Callable[[str], None]


def _noop(message: str) -> None:
    pass


class FillError(RuntimeError):
    pass


class CaptchaRequired(FillError):
    pass


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _date_text(value: str) -> str:
    text = value.strip()
    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso:
        year, month, day = iso.groups()
        return f"{day}.{month}.{year}"
    dotted = re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", text)
    if dotted:
        day, month, year = dotted.groups()
        return f"{int(day):02d}.{int(month):02d}.{year}"
    return text


def _option_text(element: WebElement) -> str:
    try:
        text_el = element.find_elements(By.CSS_SELECTOR, ".g-control-label__text")
        if text_el:
            return safe_text(text_el[0])
    except Exception:
        pass
    return safe_text(element)


class FormFiller:
    def __init__(
        self,
        driver,
        log: Log = _noop,
        timeout: int = 30,
        screenshot_dir: str | None = None,
    ) -> None:
        self.driver = driver
        self.log = log
        self.timeout = timeout
        self.screenshot_dir = screenshot_dir
        self.wait = WebDriverWait(driver, timeout)

    # ---------- helpers ----------

    def _scroll(self, element: WebElement) -> None:
        try:
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", element
            )
            time.sleep(0.15)
        except Exception:
            pass

    def _click(self, element: WebElement) -> None:
        self._scroll(element)
        try:
            element.click()
        except (ElementClickInterceptedException, StaleElementReferenceException):
            try:
                self.driver.execute_script("arguments[0].click();", element)
            except JavascriptException as exc:
                raise FillError(f"Не удалось кликнуть по элементу: {exc}") from exc

    def _set_value(self, element: WebElement, value: str) -> None:
        self._scroll(element)
        try:
            element.clear()
        except Exception:
            pass
        try:
            element.send_keys(value)
            return
        except Exception:
            pass
        self._js_set_value(element, value)

    def _js_set_value(self, element: WebElement, value: str) -> None:
        self.driver.execute_script(
            """
            const el = arguments[0];
            const value = arguments[1];
            const proto = el.tagName === 'TEXTAREA'
                ? window.HTMLTextAreaElement.prototype
                : window.HTMLInputElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
            setter.call(el, value);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            el.blur();
            """,
            element,
            value,
        )

    def _top_cards(self) -> list[WebElement]:
        cards = self.driver.find_elements(
            By.CSS_SELECTOR,
            "div.QuestionMarkup.Question, div.Series, div.SetQuestion, div.SeriesQuestion",
        )
        result = []
        for card in cards:
            try:
                ancestors = card.find_elements(
                    By.XPATH,
                    "ancestor::div["
                    "contains(@class,'Series') or "
                    "contains(@class,'SetQuestion') or "
                    "(contains(@class,'QuestionMarkup') and contains(@class,'Question'))"
                    "]",
                )
                if not ancestors:
                    result.append(card)
            except StaleElementReferenceException:
                continue
        return result

    def _card_has_id(self, card: WebElement, qid: str) -> bool:
        try:
            if card.find_elements(By.CSS_SELECTOR, f'[id="{qid}"]'):
                return True
            if card.find_elements(By.CSS_SELECTOR, f'[id="{qid}-label"]'):
                return True
            if card.find_elements(By.CSS_SELECTOR, f'[name="{qid}"]'):
                return True
            if card.find_elements(By.CSS_SELECTOR, f'[name^="{qid}."]'):
                return True
        except Exception:
            pass
        return False

    def find_card(self, question: Question) -> WebElement:
        wanted = normalize(question.label)
        last_error: Exception | None = None
        for _ in range(4):
            try:
                cards = self._top_cards()
                for card in cards:
                    if self._card_has_id(card, question.qid):
                        return card
                for card in cards:
                    try:
                        labels = card.find_elements(
                            By.CSS_SELECTOR, ".QuestionLabel-Text, .Series-Title"
                        )
                        for label in labels:
                            if wanted and normalize(safe_text(label)) == wanted:
                                return card
                    except StaleElementReferenceException:
                        continue
                if 1 <= question.index <= len(cards):
                    candidate = cards[question.index - 1]
                    candidate.tag_name
                    return candidate
            except StaleElementReferenceException as exc:
                last_error = exc
            time.sleep(0.3)
        raise FillError(
            f"Не найден вопрос «{question.label or question.qid}» на странице"
        ) from last_error

    def _find_child_card(
        self, scope: WebElement, child: Question, child_index: int
    ) -> WebElement:
        wanted = normalize(child.label)
        last_error: Exception | None = None
        for _ in range(4):
            try:
                cards = scope.find_elements(
                    By.CSS_SELECTOR, "div.QuestionMarkup.Question"
                )
                for card in cards:
                    if self._card_has_id(card, child.qid):
                        return card
                for card in cards:
                    try:
                        labels = card.find_elements(
                            By.CSS_SELECTOR, ".QuestionLabel-Text"
                        )
                        for label in labels:
                            if wanted and normalize(safe_text(label)) == wanted:
                                return card
                    except StaleElementReferenceException:
                        continue
                if 1 <= child_index <= len(cards):
                    candidate = cards[child_index - 1]
                    candidate.tag_name
                    return candidate
            except StaleElementReferenceException as exc:
                last_error = exc
            time.sleep(0.3)
        raise FillError(f"Не найден подвопрос «{child.label}»") from last_error

    # ---------- fill ----------

    def fill(self, questions: Iterable[Question], submit: bool = False) -> dict[str, Any]:
        questions = list(questions)
        pages = sorted({q.page for q in questions}) or [1]
        for page_index, page in enumerate(pages, start=1):
            page_questions = [q for q in questions if q.page == page]
            for question in page_questions:
                if question.type in {QType.STATIC, QType.HINT}:
                    continue
                if question.type == QType.CAPTCHA:
                    raise CaptchaRequired("Форма требует ручного прохождения капчи")
                card = self.find_card(question)
                self.log(
                    f"Заполняю [{question.index}] {question.type}: "
                    f"{question.label[:70]}"
                )
                self.fill_question(card, question)
            if page_index < len(pages):
                self._go_next()

        result: dict[str, Any] = {"submitted": False, "akey": None, "url": self.driver.current_url}
        if submit:
            result.update(self.submit())
        return result

    def fill_question(self, card: WebElement, question: Question) -> None:
        qtype = question.type
        value = question.answer
        if qtype in {
            QType.TEXT,
            QType.LONG_TEXT,
            QType.NUMBER,
            QType.INTEGER,
            QType.EMAIL,
            QType.PHONE,
            QType.INN,
            QType.URL,
        }:
            self._fill_text(card, question, value)
        elif qtype == QType.PAYMENT:
            self._fill_text(card, question, value)
        elif qtype == QType.SUGGEST:
            self._fill_suggest(card, question, value)
        elif qtype == QType.RADIO:
            self._fill_radio(card, question, value)
        elif qtype == QType.CHECKBOX:
            self._fill_checkbox(card, question, value)
        elif qtype == QType.DROPDOWN:
            self._fill_dropdown(card, question, value)
        elif qtype == QType.BOOLEAN:
            self._fill_boolean(card, question, value)
        elif qtype in {QType.DATE, QType.DATE_RANGE}:
            self._fill_date(card, question, value)
        elif qtype == QType.FILE:
            self._fill_file(card, question, value)
        elif qtype == QType.MATRIX:
            self._fill_matrix(card, question, value)
        elif qtype == QType.SERIES:
            self._fill_series(card, question, value)
        elif qtype == QType.STATIC or qtype == QType.HINT:
            return
        else:
            raise FillError(f"Тип вопроса пока не поддерживается: {qtype}")

    def _text_input(self, card: WebElement) -> WebElement:
        inputs = card.find_elements(
            By.CSS_SELECTOR,
            "textarea, input:not([type='hidden']):not([type='radio']):not([type='checkbox']):not([type='file'])",
        )
        if not inputs:
            raise FillError("Не найдено поле ввода")
        return inputs[0]

    def _fill_text(self, card: WebElement, question: Question, value: Any) -> None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return
        element = self._text_input(card)
        text = str(value)
        if question.type in {QType.NUMBER, QType.INTEGER, QType.PAYMENT}:
            text = text.replace(",", ".")
        if question.type == QType.LONG_TEXT and ("\n" in text or "\r" in text):
            self._js_set_value(element, text)
        else:
            self._set_value(element, text)

    def _choice_pairs(self, card: WebElement) -> list[tuple[WebElement, WebElement, str]]:
        result = []
        inputs = card.find_elements(
            By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']"
        )
        for element in inputs:
            try:
                label = element.find_element(By.XPATH, "./ancestor::label[1]")
            except NoSuchElementException:
                label = element
            result.append((element, label, _option_text(label)))
        return result

    def _select_choice(
        self, card: WebElement, question: Question, wanted: Any
    ) -> None:
        pairs = self._choice_pairs(card)
        if not pairs:
            raise FillError(f"Не найдены варианты ответа для «{question.label}»")
        position = position_value(wanted, len(pairs))
        target: tuple[WebElement, WebElement, str] | None = None
        if position is not None:
            target = pairs[position]
        else:
            text = str(wanted)
            for pair in pairs:
                if option_matches(pair[2], pair[0].get_attribute("value") or "", text):
                    target = pair
                    break
        if target is None:
            available = ", ".join(p[2] for p in pairs[:10])
            raise FillError(
                f"Вариант «{wanted}» не найден. Доступно: {available}"
            )
        self._click(target[1])
        if not target[0].is_selected():
            self._click(target[0])
        time.sleep(0.1)

    def _fill_radio(self, card: WebElement, question: Question, value: Any) -> None:
        if value is None or value == "":
            return
        self._select_choice(card, question, value)

    def _fill_checkbox(self, card: WebElement, question: Question, value: Any) -> None:
        if value is None or value == "":
            return
        other_text = ""
        if isinstance(value, dict):
            other_text = str(value.get("other") or value.get("other_text") or "")
            value = value.get("values") or value.get("value") or []
        items = _as_list(value)
        if not items:
            return
        pairs = self._choice_pairs(card)
        if not pairs:
            raise FillError(f"Не найдены варианты ответа для «{question.label}»")
        if items and str(items[0]).lower() in {"#all", "all"}:
            items = [pair[2] for pair in pairs]
        if str(items[0]).lower() in {"#first", "first"}:
            items = [pairs[0][2]]
        selected = set()
        for item in items:
            position = position_value(item, len(pairs))
            target = None
            if position is not None:
                target = pairs[position]
            else:
                for pair in pairs:
                    if option_matches(
                        pair[2], pair[0].get_attribute("value") or "", str(item)
                    ):
                        target = pair
                        break
            if target is None:
                raise FillError(f"Вариант «{item}» не найден в «{question.label}»")
            selected.add(id(target[0]))
            if not target[0].is_selected():
                self._click(target[1])
        for element, _, _ in pairs:
            if id(element) not in selected and element.is_selected():
                self._click(element)
        if other_text:
            text_inputs = card.find_elements(
                By.CSS_SELECTOR,
                "input[type='text'], textarea",
            )
            if text_inputs:
                self._set_value(text_inputs[-1], other_text)

    def _fill_dropdown(self, card: WebElement, question: Question, value: Any) -> None:
        if value is None or value == "":
            return
        native = card.find_elements(By.CSS_SELECTOR, "select")
        if native:
            select = Select(native[0])
            text = str(value)
            position = position_value(text, len(select.options))
            if position is not None:
                select.select_by_index(position)
                return
            for option in select.options:
                if option_matches(option.text, option.get_attribute("value") or "", text):
                    select.select_by_visible_text(option.text)
                    return
            raise FillError(f"Вариант «{value}» не найден в выпадающем списке")
        buttons = card.find_elements(By.CSS_SELECTOR, "button[role='combobox']")
        if not buttons:
            buttons = card.find_elements(By.CSS_SELECTOR, "[role='combobox']")
        if not buttons:
            raise FillError(f"Не найден выпадающий список «{question.label}»")
        button = buttons[0]
        self._click(button)
        time.sleep(0.4)
        filter_input = None
        for candidate in self.driver.find_elements(
            By.CSS_SELECTOR, ".g-select-filter__input"
        ):
            try:
                if candidate.is_displayed():
                    filter_input = candidate
                    break
            except StaleElementReferenceException:
                continue
        text = str(value)
        if filter_input is not None:
            try:
                filter_input.clear()
                filter_input.send_keys(text)
                time.sleep(0.8)
            except Exception:
                pass
        try:
            WebDriverWait(self.driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[role='option']"))
            )
        except TimeoutException:
            pass
        options = self.driver.find_elements(By.CSS_SELECTOR, "[role='option']")
        target = None
        for option in options:
            label = safe_text(option)
            option_value = option.get_attribute("data-value") or option.get_attribute("value") or label
            if option_matches(label, option_value, text):
                target = option
                break
        if target is None:
            available = ", ".join(safe_text(o) for o in options[:10])
            try:
                self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            except Exception:
                pass
            raise FillError(
                f"Вариант «{value}» не найден в списке. Доступно: {available}"
            )
        self._click(target)
        time.sleep(0.3)

    def _fill_suggest(self, card: WebElement, question: Question, value: Any) -> None:
        if value is None or value == "":
            return
        inputs = card.find_elements(By.CSS_SELECTOR, "input[role='combobox'], input[type='text']")
        if not inputs:
            raise FillError(f"Не найдено поле «{question.label}»")
        element = inputs[0]
        values = _as_list(value)
        for item in values:
            self._scroll(element)
            try:
                element.clear()
            except Exception:
                pass
            element.send_keys(str(item))
            time.sleep(1.0)
            options = self.driver.find_elements(By.CSS_SELECTOR, "[role='option']")
            target = None
            for option in options:
                if option_matches(safe_text(option), "", str(item)):
                    target = option
                    break
            if target is not None:
                self._click(target)
                time.sleep(0.3)
            else:
                try:
                    element.send_keys(Keys.ESCAPE)
                except Exception:
                    pass

    def _fill_boolean(self, card: WebElement, question: Question, value: Any) -> None:
        if value is None:
            return
        truthy = value is True or normalize(value) in {"да", "true", "1", "yes"}
        pairs = self._choice_pairs(card)
        if len(pairs) >= 2:
            text = str(value)
            known = any(
                option_matches(pair[2], pair[0].get_attribute("value") or "", text)
                for pair in pairs
            )
            self._select_choice(
                card, question, text if known else ("Да" if truthy else "Нет")
            )
            return
        if pairs:
            element, label, _ = pairs[0]
            if truthy and not element.is_selected():
                self._click(label)
            elif not truthy and element.is_selected():
                self._click(label)
            return
        switches = card.find_elements(By.CSS_SELECTOR, "[role='switch'], button[aria-checked]")
        if switches:
            element = switches[0]
            checked = (element.get_attribute("aria-checked") or "").lower() == "true"
            if checked != truthy:
                self._click(element)
            return
        raise FillError(f"Не найден переключатель «{question.label}»")

    def _fill_date(self, card: WebElement, question: Question, value: Any) -> None:
        if value is None or value == "":
            return
        inputs = card.find_elements(By.CSS_SELECTOR, "input")
        inputs = [i for i in inputs if (i.get_attribute("type") or "").lower() != "hidden"]
        if not inputs:
            raise FillError(f"Не найдено поле даты «{question.label}»")
        if isinstance(value, dict):
            pairs = [("from", 0), ("to", 1)]
            for key, index in pairs:
                raw = value.get(key)
                if raw and index < len(inputs):
                    self._set_date(inputs[index], str(raw))
        else:
            self._set_date(inputs[0], str(value))

    def _set_date(self, element: WebElement, value: str) -> None:
        text = _date_text(value)
        self._scroll(element)
        input_type = (element.get_attribute("type") or "").lower()
        if input_type == "date":
            try:
                year, month, day = text.split(".")
                self._js_set_value(element, f"{year}-{month}-{day}")
                time.sleep(0.2)
                if element.get_attribute("value"):
                    return
            except Exception:
                pass
        digits = re.sub(r"\D", "", text)
        if not digits:
            raise FillError(f"Некорректная дата: {value}")
        try:
            element.click()
            element.send_keys(*([Keys.ARROW_LEFT] * 6))
            element.send_keys(digits)
            self.driver.execute_script("arguments[0].blur();", element)
            time.sleep(0.4)
        except Exception as exc:
            raise FillError(f"Не удалось установить дату: {exc}") from exc

    def _fill_file(self, card: WebElement, question: Question, value: Any) -> None:
        paths = [str(p) for p in _as_list(value)]
        if not paths:
            return
        for path in paths:
            if not os.path.exists(path):
                raise FillError(f"Файл не найден: {path}")
        inputs = card.find_elements(By.CSS_SELECTOR, "input[type='file']")
        if not inputs:
            raise FillError(f"Не найдено поле загрузки файла «{question.label}»")
        element = inputs[0]
        try:
            self.driver.execute_script(
                """
                arguments[0].style.display = 'block';
                arguments[0].style.visibility = 'visible';
                arguments[0].style.opacity = '1';
                arguments[0].style.width = '1px';
                arguments[0].style.height = '1px';
                """,
                element,
            )
        except Exception:
            pass
        if len(paths) == 1:
            element.send_keys(paths[0])
        else:
            element.send_keys("\n".join(paths))
        time.sleep(0.8)

    def _fill_matrix(self, card: WebElement, question: Question, value: Any) -> None:
        if value is None or value == "":
            return
        if not isinstance(value, dict):
            value = {row.id or row.label: value for row in question.rows}
        for row in question.rows:
            wanted = value.get(row.id, value.get(row.label))
            if wanted in (None, ""):
                continue
            row_element = None
            for candidate in card.find_elements(By.CSS_SELECTOR, ".MatrixQuestion-Row"):
                titles = candidate.find_elements(By.CSS_SELECTOR, ".MatrixQuestion-RowTitle")
                title = safe_text(titles[0]) if titles else ""
                if normalize(title) == normalize(row.label):
                    row_element = candidate
                    break
            if row_element is None:
                raise FillError(f"Не найдена строка шкалы «{row.label}»")
            buttons = row_element.find_elements(
                By.CSS_SELECTOR, ".MatrixQuestion-Button, [role='radio']"
            )
            target = None
            position = position_value(wanted, len(buttons))
            if position is not None and position < len(buttons):
                target = buttons[position]
            else:
                for button in buttons:
                    if option_matches(safe_text(button), button.get_attribute("value") or "", str(wanted)):
                        target = button
                        break
            if target is None:
                raise FillError(
                    f"Оценка «{wanted}» не найдена для строки «{row.label}»"
                )
            self._click(target)
            time.sleep(0.1)

    def _series_instances(self, card: WebElement, question: Question) -> list[WebElement]:
        selectors = [
            ".Series-Card",
            ".Series-Item",
            ".SetQuestion-Item",
            "[class*='SeriesItem']",
            "[class*='SetQuestion-Item']",
            "[class*='Series-Item']",
        ]
        for selector in selectors:
            found = card.find_elements(By.CSS_SELECTOR, selector)
            if found:
                return found
        return []

    def _fill_series(self, card: WebElement, question: Question, value: Any) -> None:
        instances = value if isinstance(value, list) else []
        if not instances:
            return
        add_button = None
        for button in card.find_elements(By.CSS_SELECTOR, "button"):
            text = normalize(safe_text(button))
            if ("добав" in text or "еще" in text) and "файл" not in text:
                add_button = button
                break
        instance_elements = self._series_instances(card, question)
        while len(instance_elements) < len(instances) and add_button is not None:
            self._click(add_button)
            time.sleep(0.7)
            instance_elements = self._series_instances(card, question)
            if not instance_elements:
                break
        nested_cards = card.find_elements(By.CSS_SELECTOR, "div.QuestionMarkup.Question")
        child_count = len(question.children)
        if not child_count:
            return
        if instance_elements:
            for index, instance in enumerate(instances):
                if index >= len(instance_elements):
                    break
                scope = instance_elements[index]
                self._fill_series_instance(scope, question, instance)
            return
        if len(nested_cards) >= child_count:
            for index, instance in enumerate(instances):
                start = index * child_count
                end = start + child_count
                if end > len(nested_cards):
                    break
                scope = nested_cards[start]
                parent = scope.find_element(By.XPATH, "./..")
                self._fill_series_instance(parent, question, instance)

    def _fill_series_instance(
        self, scope: WebElement, question: Question, instance: dict[str, Any]
    ) -> None:
        for child_index, child in enumerate(question.children, start=1):
            child_value = instance.get(child.qid)
            if child_value is None:
                for key, candidate in instance.items():
                    if normalize(key) == normalize(child.label):
                        child_value = candidate
                        break
            child.answer = child_value
            child_card = self._find_child_card(scope, child, child_index)
            self.fill_question(child_card, child)

    def _go_next(self) -> None:
        for button in self.driver.find_elements(By.CSS_SELECTOR, "button"):
            text = normalize(safe_text(button))
            if text in {"далее", "продолжить", "next", "continue"}:
                if button.is_displayed() and button.is_enabled():
                    self._click(button)
                    time.sleep(1.5)
                    return
        raise FillError("Не найдена кнопка перехода на следующую страницу")

    def submit(self) -> dict[str, Any]:
        target = None
        for button in self.driver.find_elements(By.CSS_SELECTOR, "button"):
            text = normalize(safe_text(button))
            if text in {"отправить", "submit", "готово"}:
                if button.is_displayed() and button.is_enabled():
                    target = button
                    break
        if target is None:
            raise FillError("Не найдена кнопка «Отправить»")
        self._click(target)
        try:
            WebDriverWait(self.driver, 60).until(
                lambda d: "/success/" in d.current_url
                or "ответ отправлен" in normalize(d.find_element(By.TAG_NAME, "body").text)
            )
        except TimeoutException:
            self._snapshot("submit_timeout")
            raise FillError("Форма не показала успешную отправку")
        url = self.driver.current_url
        akey = parse_qs(urlparse(url).query).get("akey", [None])[0]
        return {"submitted": True, "akey": akey, "url": url}

    def _snapshot(self, name: str) -> None:
        if not self.screenshot_dir:
            return
        try:
            os.makedirs(self.screenshot_dir, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            self.driver.save_screenshot(
                os.path.join(self.screenshot_dir, f"{name}_{stamp}.png")
            )
            with open(
                os.path.join(self.screenshot_dir, f"{name}_{stamp}.html"),
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write(self.driver.page_source)
        except Exception:
            pass
