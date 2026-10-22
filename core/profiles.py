from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from typing import Any, Iterable

from .model import Question, apply_answers, collect_answers, fingerprint
from .types import normalize


def profile_path_for(profile_dir: str, url: str) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    return os.path.join(profile_dir, f"autosave_{digest}.json")


def save_profile(
    path: str,
    url: str,
    questions: Iterable[Question],
    answers: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    questions = list(questions)
    payload = {
        "version": 1,
        "url": url,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "fingerprint": fingerprint(questions),
        "meta": meta or {},
        "answers": answers if answers is not None else collect_answers(questions),
        "labels": {q.qid: q.label for q in questions},
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_profile(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or "answers" not in data:
        raise ValueError("Файл профиля не похож на профиль ответов")
    return data


def apply_profile(questions: Iterable[Question], profile: dict[str, Any]) -> int:
    questions = list(questions)
    answers = profile.get("answers") or {}
    if not isinstance(answers, dict):
        raise ValueError("В профиле отсутствует объект answers")
    apply_answers(questions, answers)

    labels = profile.get("labels") or {}
    label_to_qid = {
        normalize(label): qid for qid, label in labels.items() if label
    }
    current_by_label = {
        normalize(q.label): q for q in questions if q.label
    }
    applied = 0
    for q in questions:
        if q.answer is not None:
            applied += 1
            continue
        old_qid = label_to_qid.get(normalize(q.label))
        if old_qid and old_qid in answers:
            q.answer = answers[old_qid]
            applied += 1
            continue
        fallback = current_by_label.get(normalize(q.label))
        if fallback is not None and fallback.answer is not None:
            q.answer = fallback.answer
            applied += 1
    return applied


def profile_matches(profile: dict[str, Any], questions: Iterable[Question]) -> bool:
    return profile.get("fingerprint") == fingerprint(list(questions))
