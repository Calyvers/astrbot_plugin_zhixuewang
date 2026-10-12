"""Fallback score extraction for exams whose report omits ``userScore``.

The report API is authoritative when it returns a score.  This module only
reads the matching answer sheet (same exam_id + paper_id) and never derives a
score from rank/trend percentages or adds estimated subject scores together.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FallbackScore:
    score: float
    standard_score: float | None = None
    source: str = "答题卡"


def _objects(value: Any):
    """Yield nested dict/list objects, decoding JSON strings on the way."""
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return
        yield from _objects(decoded)
    elif isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _objects(child)


def extract_total_score(payload: Any) -> FallbackScore | None:
    """Extract the explicit total score from a checksheet response.

    ``sheetDatas`` is sometimes a JSON string nested several levels deep.
    Prefer a record labelled ``总分``; otherwise accept a record carrying a
    marking source.  Do not sum question/subtopic scores.
    """
    candidates = list(_objects(payload))
    for obj in candidates:
        score = obj.get("score")
        if (obj.get("dispTitle") == "总分"
                and isinstance(score, (int, float))
                and not isinstance(score, bool)):
            return FallbackScore(float(score), _number(obj.get("standardScore")))
    # Do not treat question-level scores as the paper total.  A question
    # may also carry ``scoreSource``; only an explicitly labelled total is
    # safe to use as the fallback subject score.
    return None


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def get_fallback_score(account, exam_id: str, paper_id: str) -> FallbackScore | None:
    """Fetch only the exact answer sheet matching exam_id and paper_id."""
    payload = account.get_sheet_payload(exam_id, paper_id)
    if not payload:
        return None
    return extract_total_score(payload)
