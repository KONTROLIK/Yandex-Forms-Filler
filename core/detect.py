from __future__ import annotations

import re
import time
from typing import Callable

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from .model import Option, Question, ScaleRow
from .types import (
    DOM_TYPE_MAP,
    QType,
    SERIES_MARKERS,
    normalize,
)

Log = Callable[[str], None]


def _noop(message: str) -> None:
    pass


def safe_text(element: WebElement | None) -> str:
    if element is None:
        return ""
    try:
        return (element.get_attribute("innerText") or element.text or "").strip()
    except StaleElementReferenceException:
        return ""


def _first(card: WebElement, selector: str) -> WebElement | None:
    found = card.find_elements(By.CSS_SELECTOR, selector)
    return found[0] if found else None


def _classes(card: WebElement) -> set[str]:
    return set((card.get_attribute("class") or "").split())


def _label_element(card: WebElement) -> WebElement | None:
    return _first(card, ".QuestionLabel")


def _label_text(card: WebElement) -> str:
    series_title = _first(card, ".Series-Title")
    if series_title is not None:
        return safe_text(series_title)
    element = _first(card, ".QuestionLabel-Text")
    if element is not None:
        return safe_text(element)
    label = _label_element(card)
    return safe_text(label)


def _valid_id(value: str | None) -> str:
    text = (value or "").strip()
    if text.casefold() in {"undefined", "null", "none", "nan"}:
        return ""
    return text


def _help_text(card: WebElement) -> str:
    return safe_text(_first(card, ".QuestionLayout-Comment"))


def _is_required(card: WebElement) -> bool:
    if card.find_elements(By.CSS_SELECTOR, ".QuestionLabel-Required"):
        return True
    if card.find_elements(By.CSS_SELECTOR, "[aria-required='true']"):
        return True
    if card.find_elements(By.CSS_SELECTOR, "input[required], textarea[required]"):
        return True
    return False


def _label_qid(card: WebElement) -> str:
    label = _label_element(card)
    if label is None:
        return ""
    label_id = (label.get_attribute("id") or "").strip()
    if label_id.endswith("-label"):
        label_id = label_id[: -len("-label")]
    return _valid_id(label_id)


def _input_elements(card: WebElement) -> list[WebElement]:
    return card.find_elements(
        By.CSS_SELECTOR,
        "input:not([type='hidden']), textarea, select",
    )


def _first_input(card: WebElement) -> WebElement | None:
    inputs = _input_elements(card)
    return inputs[0] if inputs else None


def _all_inputs(card: WebElement) -> list[WebElement]:
    return card.find_elements(By.CSS_SELECTOR, "input, textarea, select")


def _hidden_input(card: WebElement) -> WebElement | None:
    inputs = card.find_elements(By.CSS_SELECTOR, "input[type='hidden']")
    return inputs[0] if inputs else None


def _qid(card: WebElement, page: int, index: int) -> str:
    if _classes(card) & SERIES_MARKERS:
        for element in card.find_elements(By.CSS_SELECTOR, "input[name]"):
            name = element.get_attribute("name") or ""
            match = re.match(r"(answer_series_[^.]+)", name)
            if match:
                return match.group(1)
    from_label = _label_qid(card)
    if from_label:
        return from_label
    group = card.find_elements(By.CSS_SELECTOR, "[role='radiogroup'][id]")
    if group:
        return group[0].get_attribute("id") or ""
    for selector in (
        "button[role='combobox'][id]",
        "input:not([type='hidden'])[id]",
        "textarea[id]",
        "select[id]",
        "input[type='hidden'][name]",
    ):
        found = card.find_elements(By.CSS_SELECTOR, selector)
        if found:
            value = _valid_id(
                found[0].get_attribute("id") or found[0].get_attribute("name")
            )
            if value:
                return value
    return f"q_{page}_{index}"


def detect_type(card: WebElement) -> str:
    classes = _classes(card)
    if classes & SERIES_MARKERS:
        return QType.SERIES
    for class_name, qtype in DOM_TYPE_MAP.items():
        if class_name in classes:
            return qtype
    if "Hint" in classes or any("Hint" in c for c in classes):
        return QType.HINT

    inputs = _input_elements(card)
    if not inputs and not card.find_elements(By.CSS_SELECTOR, "[role='radiogroup']"):
        return QType.STATIC
    if inputs and inputs[0].tag_name.lower() == "textarea":
        return QType.LONG_TEXT
    if inputs:
        return _text_subtype(card, inputs[0])
    return QType.STATIC


def _text_subtype(card: WebElement, element: WebElement) -> str:
    tag = element.tag_name.lower()
    if tag == "textarea":
        return QType.LONG_TEXT
    input_type = (element.get_attribute("type") or "text").lower()
    input_mode = (element.get_attribute("inputmode") or "").lower()
    label = normalize(_label_text(card))
    maxlength = (element.get_attribute("maxlength") or "").strip()
    step = (element.get_attribute("step") or "").strip()

    if "инн" in label:
        return QType.INN
    if input_type == "email" or "почта" in label or "email" in label:
        return QType.EMAIL
    if input_type == "tel" or "телефон" in label:
        return QType.PHONE
    if input_type == "url" or "ссылка" in label or "сайт" in label:
        return QType.URL
    if input_type == "number":
        return QType.NUMBER
    if input_mode == "decimal":
        return QType.NUMBER
    if input_mode == "numeric":
        if maxlength in {"10", "12"} and "инн" in label:
            return QType.INN
        return QType.INTEGER
    if step and "." in step:
        return QType.NUMBER
    return QType.TEXT


def _option_from_input(element: WebElement) -> Option:
    label = ""
    try:
        parent = element.find_element(By.XPATH, "./ancestor::label[1]")
        text_el = parent.find_elements(By.CSS_SELECTOR, ".g-control-label__text")
        label = safe_text(text_el[0]) if text_el else safe_text(parent)
    except Exception:
        label = element.get_attribute("value") or ""
    value = element.get_attribute("value") or ""
    disabled = (element.get_attribute("disabled") is not None) or (
        element.get_attribute("aria-disabled") == "true"
    )
    nlabel = normalize(label)
    other = nlabel in {"другое", "иное", "свой вариант"} or "другое" in nlabel
    return Option(value=value, label=label or value, disabled=disabled, other=other)


def _choice_options(card: WebElement) -> list[Option]:
    inputs = card.find_elements(
        By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']"
    )
    options = []
    seen = set()
    for element in inputs:
        option = _option_from_input(element)
        key = (option.value, normalize(option.label))
        if key in seen:
            continue
        seen.add(key)
        options.append(option)
    return options


def _collect_dropdown_options(
    driver, card: WebElement, log: Log = _noop
) -> tuple[list[Option], bool]:
    button = card.find_elements(By.CSS_SELECTOR, "button[role='combobox']")
    if not button:
        return [], False
    element = button[0]
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", element
        )
        time.sleep(0.2)
        driver.execute_script("arguments[0].click();", element)
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[role='option']"))
        )
        time.sleep(0.4)
        filter_inputs = card.find_elements(By.CSS_SELECTOR, ".g-select-filter__input")
        if not filter_inputs:
            filter_inputs = driver.find_elements(
                By.CSS_SELECTOR, ".g-select-filter__input"
            )
        filterable = bool(filter_inputs)
        options: list[Option] = []
        seen: set[str] = set()

        def collect() -> None:
            for option_el in driver.find_elements(
                By.CSS_SELECTOR, "[role='option']"
            ):
                label = safe_text(option_el)
                nlabel = normalize(label)
                if (
                    not label
                    or nlabel in seen
                    or nlabel in {"-", "—", "–", "не выбрано", "выберите вариант"}
                    or "не выбрано" in nlabel
                ):
                    continue
                seen.add(nlabel)
                value = (
                    option_el.get_attribute("data-value")
                    or option_el.get_attribute("value")
                    or label
                )
                options.append(Option(value=value, label=label))

        collect()
        for _ in range(80):
            state = driver.execute_script(
                """
                const list = document.querySelector('.g-select-list');
                if (!list) return {done: true};
                const nodes = [list, ...list.querySelectorAll('*')];
                let scroller = null;
                for (const node of nodes) {
                    if (node.scrollHeight > node.clientHeight + 2) {
                        if (!scroller || node.scrollHeight > scroller.scrollHeight) {
                            scroller = node;
                        }
                    }
                }
                if (!scroller) return {done: true};
                const max = scroller.scrollHeight - scroller.clientHeight;
                const step = Math.max(120, Math.floor(scroller.clientHeight * 0.75));
                const pos = scroller.scrollTop < max
                    ? Math.min(max, scroller.scrollTop + step)
                    : max;
                scroller.scrollTop = pos;
                scroller.dispatchEvent(new Event('scroll', {bubbles: true}));
                return {done: pos >= max};
                """
            )
            time.sleep(0.15)
            collect()
            if state.get("done"):
                break
        return options, filterable
    except Exception as exc:
        log(f"Не удалось прочитать варианты dropdown: {type(exc).__name__}")
        return [], True
    finally:
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        except Exception:
            pass


def _matrix_parts(card: WebElement) -> tuple[list[ScaleRow], list[Option]]:
    rows: list[ScaleRow] = []
    for row in card.find_elements(By.CSS_SELECTOR, ".MatrixQuestion-Row"):
        title = row.find_elements(By.CSS_SELECTOR, ".MatrixQuestion-RowTitle")
        label = safe_text(title[0]) if title else ""
        row_id = (title[0].get_attribute("id") if title else "") or label
        rows.append(ScaleRow(id=row_id, label=label))
    columns: list[Option] = []
    seen = set()
    for button in card.find_elements(By.CSS_SELECTOR, ".MatrixQuestion-Button"):
        label = safe_text(button)
        if not label or normalize(label) in seen:
            continue
        seen.add(normalize(label))
        value = button.get_attribute("data-value") or label
        columns.append(Option(value=value, label=label))
    if not columns:
        for element in card.find_elements(By.CSS_SELECTOR, "[role='radio']"):
            label = safe_text(element)
            if label and normalize(label) not in seen:
                seen.add(normalize(label))
                columns.append(Option(value=label, label=label))
    return rows, columns


def _series_add_button(card: WebElement) -> WebElement | None:
    for button in card.find_elements(By.CSS_SELECTOR, "button"):
        text = normalize(safe_text(button))
        if ("добав" in text or "еще" in text) and "файл" not in text:
            return button
    return None


def parse_question(
    driver,
    card: WebElement,
    index: int,
    page: int = 1,
    log: Log = _noop,
    collect_dropdown: bool = True,
) -> Question:
    qtype = detect_type(card)
    label = _label_text(card)
    help_text = _help_text(card)
    required = _is_required(card)
    qid = _qid(card, page, index)

    question = Question(
        qid=qid,
        label=label,
        type=qtype,
        required=required,
        help=help_text,
        page=page,
        index=index,
        placeholder="",
        input_id="",
        input_name="",
        input_type="",
    )

    inputs = _input_elements(card)
    first_input = inputs[0] if inputs else None
    if first_input is not None:
        question.input_id = first_input.get_attribute("id") or ""
        question.input_name = first_input.get_attribute("name") or ""
        question.input_type = first_input.get_attribute("type") or ""
        question.placeholder = first_input.get_attribute("placeholder") or ""
        for attr in ("min", "max", "step"):
            raw = first_input.get_attribute(attr)
            if raw not in (None, ""):
                try:
                    number = float(raw)
                except ValueError:
                    continue
                if attr == "min":
                    question.min_value = number
                elif attr == "max":
                    question.max_value = number
                else:
                    question.step = number
        maxlength = first_input.get_attribute("maxlength")
        if maxlength not in (None, ""):
            question.extra["maxlength"] = maxlength
        if qtype == QType.TEXT and first_input.tag_name.lower() == "textarea":
            question.type = QType.LONG_TEXT

    if qtype in {QType.RADIO, QType.CHECKBOX, QType.BOOLEAN}:
        question.options = _choice_options(card)
        if qtype == QType.CHECKBOX:
            question.multiple = True
        if not question.options and first_input is not None:
            value = first_input.get_attribute("value") or ""
            question.options = [Option(value=value, label=value or "Да")]
        if (
            qtype == QType.BOOLEAN
            and len(question.options) == 1
            and normalize(question.options[0].label) == normalize(label)
        ):
            question.options[0].label = "Да"

    if qtype == QType.DROPDOWN:
        if collect_dropdown:
            options, filterable = _collect_dropdown_options(driver, card, log)
            question.options = options
            question.filterable = filterable
        else:
            question.filterable = True
        hidden = _hidden_input(card)
        if hidden is not None:
            question.input_name = hidden.get_attribute("name") or question.input_name

    if qtype == QType.SUGGEST:
        question.filterable = True

    if qtype == QType.FILE:
        file_input = card.find_elements(By.CSS_SELECTOR, "input[type='file']")
        if file_input:
            question.multiple = file_input[0].get_attribute("multiple") is not None
            question.accept = file_input[0].get_attribute("accept") or ""
            question.input_id = file_input[0].get_attribute("id") or question.input_id
            question.input_name = (
                file_input[0].get_attribute("name") or question.input_name
            )

    if qtype == QType.DATE:
        date_inputs = [
            element
            for element in card.find_elements(By.CSS_SELECTOR, "input")
            if (element.get_attribute("type") or "").lower() != "hidden"
        ]
        if len(date_inputs) >= 2:
            question.type = QType.DATE_RANGE
            question.extra["date_inputs"] = len(date_inputs)
        if date_inputs:
            question.input_type = date_inputs[0].get_attribute("type") or ""

    if qtype == QType.PAYMENT:
        currency = _first(card, ".PaymentQuestion-Currency")
        question.currency = safe_text(currency)

    if qtype == QType.MATRIX:
        question.rows, question.columns = _matrix_parts(card)
        if not question.options:
            question.options = list(question.columns)

    if qtype == QType.SERIES:
        add_button = _series_add_button(card)
        if add_button is not None:
            question.extra["add_button"] = True

        def series_scope() -> WebElement:
            cards = card.find_elements(By.CSS_SELECTOR, ".Series-Card")
            return cards[0] if cards else card

        children = series_scope().find_elements(
            By.CSS_SELECTOR, "div.QuestionMarkup.Question"
        )
        if not children and add_button is not None:
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", add_button
                )
                time.sleep(0.2)
                driver.execute_script("arguments[0].click();", add_button)
                time.sleep(1.0)
                children = series_scope().find_elements(
                    By.CSS_SELECTOR, "div.QuestionMarkup.Question"
                )
            except Exception as exc:
                log(f"Не удалось раскрыть серию: {type(exc).__name__}")
        question.children = [
            parse_question(
                driver,
                child,
                child_index,
                page=page,
                log=log,
                collect_dropdown=collect_dropdown,
            )
            for child_index, child in enumerate(children, start=1)
        ]

    if qtype == QType.STATIC and not label and help_text:
        question.label = help_text

    return question


def parse_current_page(
    driver,
    page: int = 1,
    log: Log = _noop,
    collect_dropdown: bool = True,
) -> list[Question]:
    cards = driver.find_elements(
        By.CSS_SELECTOR,
        "div.QuestionMarkup.Question, div.Series, div.SetQuestion, div.SeriesQuestion",
    )
    top_level: list[WebElement] = []
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
                top_level.append(card)
        except StaleElementReferenceException:
            continue

    questions: list[Question] = []
    for index, card in enumerate(top_level, start=1):
        try:
            question = parse_question(
                driver,
                card,
                index,
                page=page,
                log=log,
                collect_dropdown=collect_dropdown,
            )
            questions.append(question)
            log(f"[{index}] {question.type}: {question.label[:80]}")
        except Exception as exc:
            log(f"Ошибка разбора вопроса {index}: {type(exc).__name__}: {exc}")
    return questions


def _scroll_page(driver) -> None:
    try:
        height = driver.execute_script("return document.body.scrollHeight") or 0
        position = 0
        while position < height:
            position += 800
            driver.execute_script(f"window.scrollTo(0, {position});")
            time.sleep(0.15)
            height = driver.execute_script("return document.body.scrollHeight") or height
        driver.execute_script("window.scrollTo(0, 0);")
    except Exception:
        pass


def _next_button(driver) -> WebElement | None:
    buttons = driver.find_elements(By.CSS_SELECTOR, "button")
    for button in buttons:
        try:
            text = normalize(safe_text(button))
        except StaleElementReferenceException:
            continue
        if text in {"далее", "продолжить", "next", "continue"}:
            if button.is_displayed() and button.is_enabled():
                return button
    return None


def discover_form(
    driver,
    url: str,
    log: Log = _noop,
    max_pages: int = 20,
    collect_dropdown: bool = True,
    timeout: int = 45,
) -> tuple[list[Question], dict]:
    from .driver import open_url

    open_url(driver, url, log=log, timeout=timeout)
    _scroll_page(driver)
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.QuestionMarkup.Question")
            )
        )
    except TimeoutException as exc:
        raise RuntimeError("На странице не найдены вопросы Яндекс Форм") from exc

    all_questions: list[Question] = []
    pages = 0
    page = 1
    first_qid = ""
    while page <= max_pages:
        questions = parse_current_page(
            driver, page=page, log=log, collect_dropdown=collect_dropdown
        )
        if not questions:
            break
        pages = page
        all_questions.extend(questions)
        current_first = questions[0].qid
        if page == 1:
            first_qid = current_first
        next_button = _next_button(driver)
        if next_button is None:
            break
        log(f"Переход на страницу {page + 1}")
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", next_button
            )
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", next_button)
        except Exception as exc:
            log(f"Не удалось нажать «Далее»: {type(exc).__name__}")
            break
        time.sleep(1.5)
        try:
            new_first = driver.find_elements(
                By.CSS_SELECTOR, "div.QuestionMarkup.Question"
            )
            new_qid = ""
            if new_first:
                new_qid = _qid(new_first[0], page + 1, 1)
            if new_qid and new_qid == first_qid:
                log("Страница не изменилась, сканирование остановлено")
                break
        except Exception:
            pass
        page += 1

    meta = {
        "url": url,
        "pages": pages or 1,
        "question_count": len(all_questions),
        "captcha": any(q.type == QType.CAPTCHA for q in all_questions),
    }
    return all_questions, meta
