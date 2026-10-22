from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from .types import QType, normalize


@dataclass
class Option:
    value: str = ""
    label: str = ""
    disabled: bool = False
    other: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "label": self.label,
            "disabled": self.disabled,
            "other": self.other,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Option":
        return cls(
            value=str(data.get("value", "")),
            label=str(data.get("label", "")),
            disabled=bool(data.get("disabled", False)),
            other=bool(data.get("other", False)),
        )


@dataclass
class ScaleRow:
    id: str = ""
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScaleRow":
        return cls(id=str(data.get("id", "")), label=str(data.get("label", "")))


@dataclass
class Question:
    qid: str
    label: str
    type: str
    required: bool = False
    help: str = ""
    page: int = 1
    index: int = 0
    options: list[Option] = field(default_factory=list)
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    rows: list[ScaleRow] = field(default_factory=list)
    columns: list[Option] = field(default_factory=list)
    children: list["Question"] = field(default_factory=list)
    multiple: bool = False
    min_selected: int | None = None
    max_selected: int | None = None
    placeholder: str = ""
    input_id: str = ""
    input_name: str = ""
    input_type: str = ""
    accept: str = ""
    currency: str = ""
    filterable: bool = False
    is_quiz: bool = False
    answer: Any = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "qid": self.qid,
            "label": self.label,
            "type": self.type,
            "required": self.required,
            "help": self.help,
            "page": self.page,
            "index": self.index,
            "options": [o.to_dict() for o in self.options],
            "min_value": self.min_value,
            "max_value": self.max_value,
            "step": self.step,
            "rows": [r.to_dict() for r in self.rows],
            "columns": [o.to_dict() for o in self.columns],
            "children": [c.to_dict() for c in self.children],
            "multiple": self.multiple,
            "min_selected": self.min_selected,
            "max_selected": self.max_selected,
            "placeholder": self.placeholder,
            "input_id": self.input_id,
            "input_name": self.input_name,
            "input_type": self.input_type,
            "accept": self.accept,
            "currency": self.currency,
            "filterable": self.filterable,
            "is_quiz": self.is_quiz,
            "answer": self.answer,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Question":
        return cls(
            qid=str(data.get("qid", "")),
            label=str(data.get("label", "")),
            type=str(data.get("type", QType.TEXT)),
            required=bool(data.get("required", False)),
            help=str(data.get("help", "")),
            page=int(data.get("page", 1) or 1),
            index=int(data.get("index", 0) or 0),
            options=[Option.from_dict(o) for o in data.get("options", [])],
            min_value=data.get("min_value"),
            max_value=data.get("max_value"),
            step=data.get("step"),
            rows=[ScaleRow.from_dict(r) for r in data.get("rows", [])],
            columns=[Option.from_dict(o) for o in data.get("columns", [])],
            children=[cls.from_dict(c) for c in data.get("children", [])],
            multiple=bool(data.get("multiple", False)),
            min_selected=data.get("min_selected"),
            max_selected=data.get("max_selected"),
            placeholder=str(data.get("placeholder", "")),
            input_id=str(data.get("input_id", "")),
            input_name=str(data.get("input_name", "")),
            input_type=str(data.get("input_type", "")),
            accept=str(data.get("accept", "")),
            currency=str(data.get("currency", "")),
            filterable=bool(data.get("filterable", False)),
            is_quiz=bool(data.get("is_quiz", False)),
            answer=data.get("answer"),
            extra=dict(data.get("extra", {})),
        )

    @property
    def display_label(self) -> str:
        return self.label or self.help or f"Вопрос {self.index}"


@dataclass
class ValidationError:
    qid: str
    message: str
    index: int = 0


def iter_questions(questions: Iterable[Question]) -> Iterable[Question]:
    for question in questions:
        yield question
        if question.children:
            yield from iter_questions(question.children)


def fingerprint(questions: Iterable[Question]) -> str:
    payload = []
    for q in questions:
        payload.append(
            {
                "qid": q.qid,
                "label": normalize(q.label),
                "type": q.type,
                "options": [normalize(o.label) for o in q.options],
                "rows": [normalize(r.label) for r in q.rows],
                "children": [normalize(c.label) for c in q.children],
            }
        )
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def collect_answers(questions: Iterable[Question]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for q in questions:
        result[q.qid] = q.answer
    return result


def apply_answers(questions: Iterable[Question], answers: dict[str, Any]) -> None:
    by_label = {normalize(q.label): q for q in questions if q.label}
    for q in questions:
        if q.qid in answers:
            q.answer = answers[q.qid]
            continue
        match = by_label.get(normalize(q.label))
        if match is not None and match.qid in answers:
            q.answer = answers[match.qid]
