from __future__ import annotations

import os
import re
from datetime import date
from typing import Any, Iterable
from urllib.parse import urlparse

from .model import Question, ValidationError, iter_questions
from .types import QType, normalize, option_matches

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[+]?[\d\s()\-]{7,20}$")
INN_RE = re.compile(r"^\d{10}(\d{2})?$")


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _checkbox_values(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return list(value.get("values") or value.get("value") or [])
    return _as_list(value)


def is_empty(question: Question, value: Any) -> bool:
    if question.type == QType.BOOLEAN:
        return value is None
    if question.type == QType.MATRIX:
        if not isinstance(value, dict):
            return True
        return not any(v not in (None, "") for v in value.values())
    if question.type == QType.SERIES:
        return not isinstance(value, list) or len(value) == 0
    if question.type == QType.CHECKBOX:
        if isinstance(value, dict):
            return not value.get("values") and not value.get("other")
        return len(_as_list(value)) == 0
    if question.type == QType.FILE:
        return len(_as_list(value)) == 0
    if question.type == QType.DATE_RANGE:
        if isinstance(value, dict):
            return not value.get("from") and not value.get("to")
        return value in (None, "")
    return value is None or (isinstance(value, str) and not value.strip())


def _check_option(question: Question, value: Any, errors: list[ValidationError]) -> None:
    if question.type == QType.BOOLEAN and value in (True, False, 0, 1):
        return
    if question.type == QType.CHECKBOX:
        value = _checkbox_values(value)
    if value in (None, ""):
        return
    if question.filterable or question.type == QType.SUGGEST:
        return
    if not question.options:
        return
    values = _as_list(value)
    for item in values:
        text = str(item)
        if any(
            option_matches(option.label, option.value, text)
            for option in question.options
        ):
            continue
        if any(str(option.value) == text for option in question.options):
            continue
        errors.append(
            ValidationError(
                question.qid,
                f"Вариант «{text}» не найден. Доступно: "
                + ", ".join(o.label for o in question.options[:8]),
                question.index,
            )
        )


def _validate_number(question: Question, value: Any, errors: list[ValidationError]) -> None:
    if is_empty(question, value):
        return
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        errors.append(
            ValidationError(question.qid, "Введите число", question.index)
        )
        return
    if question.type == QType.INTEGER and not number.is_integer():
        errors.append(
            ValidationError(question.qid, "Нужно целое число", question.index)
        )
    if question.min_value is not None and number < question.min_value:
        errors.append(
            ValidationError(
                question.qid,
                f"Минимальное значение: {question.min_value:g}",
                question.index,
            )
        )
    if question.max_value is not None and number > question.max_value:
        errors.append(
            ValidationError(
                question.qid,
                f"Максимальное значение: {question.max_value:g}",
                question.index,
            )
        )


def _parse_date(raw: Any) -> date:
    text = str(raw).strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    match = re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", text)
    if not match:
        raise ValueError(text)
    day, month, year = match.groups()
    return date(int(year), int(month), int(day))


def _validate_date(question: Question, value: Any, errors: list[ValidationError]) -> None:
    if is_empty(question, value):
        return
    if question.type == QType.DATE_RANGE and isinstance(value, dict):
        if question.required and (not value.get("from") or not value.get("to")):
            errors.append(
                ValidationError(
                    question.qid,
                    "Укажите начало и конец диапазона дат",
                    question.index,
                )
            )
        for key, label in (("from", "начало"), ("to", "конец")):
            raw = value.get(key)
            if raw in (None, ""):
                continue
            try:
                _parse_date(raw)
            except ValueError:
                errors.append(
                    ValidationError(
                        question.qid,
                        f"Дата ({label}) должна быть в формате ДД.ММ.ГГГГ",
                        question.index,
                    )
                )
        start, end = value.get("from"), value.get("to")
        if start and end:
            try:
                if _parse_date(start) > _parse_date(end):
                    errors.append(
                        ValidationError(
                            question.qid,
                            "Начало диапазона позже конца",
                            question.index,
                        )
                    )
            except ValueError:
                pass
        return
    try:
        _parse_date(value)
    except ValueError:
        errors.append(
            ValidationError(
                question.qid,
                "Дата должна быть в формате ДД.ММ.ГГГГ",
                question.index,
            )
        )


def _validate_files(question: Question, value: Any, errors: list[ValidationError]) -> None:
    paths = [str(p) for p in _as_list(value)]
    max_mb = question.extra.get("max_size_mb")
    for path in paths:
        if not os.path.exists(path):
            errors.append(
                ValidationError(
                    question.qid, f"Файл не найден: {path}", question.index
                )
            )
            continue
        if max_mb:
            try:
                size_mb = os.path.getsize(path) / (1024 * 1024)
                if size_mb > float(max_mb):
                    errors.append(
                        ValidationError(
                            question.qid,
                            f"Файл больше {max_mb} МБ: {os.path.basename(path)}",
                            question.index,
                        )
                    )
            except OSError:
                pass


def _validate_series(question: Question, value: Any, errors: list[ValidationError]) -> None:
    instances = value if isinstance(value, list) else []
    if question.required and not instances:
        errors.append(
            ValidationError(
                question.qid, "Добавьте хотя бы один экземпляр", question.index
            )
        )
        return
    for instance_index, instance in enumerate(instances, start=1):
        if not isinstance(instance, dict):
            continue
        for child in question.children:
            child_value = instance.get(child.qid)
            if child_value is None:
                for key, candidate in instance.items():
                    if normalize(key) == normalize(child.label):
                        child_value = candidate
                        break
            child_errors = validate_question(child, child_value)
            for error in child_errors:
                errors.append(
                    ValidationError(
                        error.qid,
                        f"Экземпляр {instance_index}: {error.message}",
                        question.index,
                    )
                )


def validate_question(question: Question, value: Any) -> list[ValidationError]:
    errors: list[ValidationError] = []
    qtype = question.type

    if qtype in {QType.STATIC, QType.HINT, QType.CAPTCHA}:
        return errors

    if question.required and is_empty(question, value):
        errors.append(
            ValidationError(
                question.qid, "Обязательный вопрос не заполнен", question.index
            )
        )
        return errors

    if qtype == QType.SERIES:
        _validate_series(question, value, errors)
        return errors

    if qtype == QType.MATRIX:
        if question.required and isinstance(value, dict):
            missing = [
                row.label
                for row in question.rows
                if value.get(row.id, value.get(row.label)) in (None, "")
            ]
            if missing:
                errors.append(
                    ValidationError(
                        question.qid,
                        "Оцените все строки: " + ", ".join(missing[:5]),
                        question.index,
                    )
                )
        if isinstance(value, dict) and question.columns:
            for row, column in value.items():
                if column in (None, ""):
                    continue
                if not any(
                    option_matches(o.label, o.value, str(column))
                    for o in question.columns
                ):
                    errors.append(
                        ValidationError(
                            question.qid,
                            f"Недопустимая оценка «{column}» для строки «{row}»",
                            question.index,
                        )
                    )
        return errors

    if qtype in {QType.RADIO, QType.DROPDOWN, QType.SUGGEST, QType.BOOLEAN}:
        _check_option(question, value, errors)
        return errors

    if qtype == QType.CHECKBOX:
        items = _checkbox_values(value)
        minimum = question.min_selected or question.extra.get("min_selected")
        maximum = question.max_selected or question.extra.get("max_selected")
        if minimum is not None and len(items) < int(minimum):
            errors.append(
                ValidationError(
                    question.qid,
                    f"Выберите минимум {minimum} вариант(ов)",
                    question.index,
                )
            )
        if maximum is not None and len(items) > int(maximum):
            errors.append(
                ValidationError(
                    question.qid,
                    f"Выберите не больше {maximum} вариант(ов)",
                    question.index,
                )
            )
        _check_option(question, value, errors)
        return errors

    if qtype in {QType.NUMBER, QType.INTEGER, QType.PAYMENT}:
        _validate_number(question, value, errors)
        if qtype == QType.PAYMENT and not is_empty(question, value):
            try:
                if float(str(value).replace(",", ".")) <= 0:
                    errors.append(
                        ValidationError(
                            question.qid, "Сумма должна быть больше нуля", question.index
                        )
                    )
            except ValueError:
                pass
        return errors

    if qtype == QType.EMAIL:
        if not is_empty(question, value) and not EMAIL_RE.match(str(value).strip()):
            errors.append(
                ValidationError(question.qid, "Некорректный email", question.index)
            )
        return errors

    if qtype == QType.PHONE:
        if not is_empty(question, value) and not PHONE_RE.match(str(value).strip()):
            errors.append(
                ValidationError(question.qid, "Некорректный телефон", question.index)
            )
        return errors

    if qtype == QType.INN:
        if not is_empty(question, value) and not INN_RE.match(str(value).strip()):
            errors.append(
                ValidationError(
                    question.qid, "ИНН должен содержать 10 или 12 цифр", question.index
                )
            )
        return errors

    if qtype == QType.URL:
        if not is_empty(question, value):
            parsed = urlparse(str(value).strip())
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                errors.append(
                    ValidationError(
                        question.qid, "Ссылка должна начинаться с http:// или https://", question.index
                    )
                )
        return errors

    if qtype in {QType.DATE, QType.DATE_RANGE}:
        _validate_date(question, value, errors)
        return errors

    if qtype == QType.FILE:
        _validate_files(question, value, errors)
        return errors

    if qtype in {QType.TEXT, QType.LONG_TEXT}:
        max_length = question.extra.get("maxlength")
        if max_length and value is not None:
            try:
                if len(str(value)) > int(max_length):
                    errors.append(
                        ValidationError(
                            question.qid,
                            f"Максимум {max_length} символов",
                            question.index,
                        )
                    )
            except ValueError:
                pass
    return errors


def validate_questions(questions: Iterable[Question]) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for question in questions:
        errors.extend(validate_question(question, question.answer))
    return errors


def first_error_by_qid(errors: Iterable[ValidationError]) -> dict[str, str]:
    result: dict[str, str] = {}
    for error in errors:
        result.setdefault(error.qid, error.message)
    return result
