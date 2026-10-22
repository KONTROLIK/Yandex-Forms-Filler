from __future__ import annotations

import re
from enum import StrEnum


class QType(StrEnum):
    TEXT = "text"
    LONG_TEXT = "long_text"
    NUMBER = "number"
    INTEGER = "integer"
    EMAIL = "email"
    PHONE = "phone"
    INN = "inn"
    URL = "url"
    RADIO = "radio"
    CHECKBOX = "checkbox"
    DROPDOWN = "dropdown"
    SUGGEST = "suggest"
    PAYMENT = "payment"
    FILE = "file"
    DATE = "date"
    DATE_RANGE = "date_range"
    MATRIX = "matrix"
    BOOLEAN = "boolean"
    SERIES = "series"
    STATIC = "static"
    HINT = "hint"
    CAPTCHA = "captcha"


TYPE_LABELS: dict[str, str] = {
    QType.TEXT: "Короткий текст",
    QType.LONG_TEXT: "Длинный текст",
    QType.NUMBER: "Число",
    QType.INTEGER: "Целое число",
    QType.EMAIL: "Почта",
    QType.PHONE: "Телефон",
    QType.INN: "ИНН",
    QType.URL: "Ссылка",
    QType.RADIO: "Один вариант",
    QType.CHECKBOX: "Несколько вариантов",
    QType.DROPDOWN: "Выпадающий список",
    QType.SUGGEST: "Города и страны",
    QType.PAYMENT: "Оплата",
    QType.FILE: "Файл",
    QType.DATE: "Дата",
    QType.DATE_RANGE: "Диапазон дат",
    QType.MATRIX: "Оценка по шкале",
    QType.BOOLEAN: "Да/Нет",
    QType.SERIES: "Серия вопросов",
    QType.STATIC: "Текст без вопроса",
    QType.HINT: "Хинт",
    QType.CAPTCHA: "Капча",
}

TEXT_LIKE = {
    QType.TEXT,
    QType.LONG_TEXT,
    QType.NUMBER,
    QType.INTEGER,
    QType.EMAIL,
    QType.PHONE,
    QType.INN,
    QType.URL,
    QType.PAYMENT,
}

CHOICE_LIKE = {
    QType.RADIO,
    QType.DROPDOWN,
    QType.SUGGEST,
    QType.BOOLEAN,
}

NO_ANSWER = {QType.STATIC, QType.HINT}

DOM_TYPE_MAP = {
    "TextQuestion": QType.TEXT,
    "IntegerQuestion": QType.INTEGER,
    "RadioQuestion": QType.RADIO,
    "CheckboxQuestion": QType.CHECKBOX,
    "DropdownQuestion": QType.DROPDOWN,
    "BooleanQuestion": QType.BOOLEAN,
    "MatrixQuestion": QType.MATRIX,
    "FileQuestion": QType.FILE,
    "DateQuestion": QType.DATE,
    "SuggestQuestion": QType.SUGGEST,
    "PaymentQuestion": QType.PAYMENT,
    "CaptchaQuestion": QType.CAPTCHA,
}

SERIES_MARKERS = {"Series", "SetQuestion", "SeriesQuestion"}


def normalize(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.replace("ё", "е").replace("Ё", "Е")
    text = re.sub(r"\s+", " ", text)
    return text.strip().casefold()


def option_matches(option_label: str, option_value: str, wanted: str) -> bool:
    nw = normalize(wanted)
    nl = normalize(option_label)
    nv = normalize(option_value)
    if not nw:
        return False
    if nw in (nl, nv):
        return True
    if len(nw) >= 2 and (nw in nl or nl in nw):
        return True
    if len(nw) >= 2 and nv and (nw in nv or nv in nw):
        return True
    return False


def position_value(value: object, count: int) -> int | None:
    if not isinstance(value, str):
        return None
    raw = value.strip().lower()
    if raw in {"#first", "#1", "first"}:
        return 0
    if raw in {"#last", "last"}:
        return max(0, count - 1)
    if raw.startswith("#") and raw[1:].isdigit():
        idx = int(raw[1:]) - 1
        if 0 <= idx < count:
            return idx
    if raw.isdigit() and 1 <= int(raw) <= count:
        return int(raw) - 1
    return None
