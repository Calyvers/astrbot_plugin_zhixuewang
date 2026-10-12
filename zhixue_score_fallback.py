"""Fallback score extraction for exams whose report omits ``userScore``.

The report API is authoritative when it returns a score.  This module only
reads the matching answer sheet (same exam_id + paper_id) and never derives a
score from rank/trend percentages or adds estimated subject scores together.
"""
from __future__ import annotations

import json
import math
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
    Only accept records labelled ``总分``. Do not mistake question scores
    for totals, even when they carry a marking source.
    """
    candidates = list(_objects(payload))
    for obj in candidates:
        score = obj.get("score")
        if (obj.get("dispTitle") == "总分"
                and isinstance(score, (int, float))
                and not isinstance(score, bool) and math.isfinite(score) and score >= 0):
            return FallbackScore(float(score), _number(obj.get("standardScore")))
    # Do not treat question-level scores as the paper total.  A question
    # may also carry ``scoreSource``; only an explicitly labelled total is
    # safe to use as the fallback subject score.
    return None


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def extract_computed_score(payload: Any, expected_full=None) -> FallbackScore | None:
    """Sum unique scored questions only when their maxima cover report full score.

    Missing question totals are not replaced with partial step scores. Unknown
    schemas, duplicate identities, invalid values or incomplete coverage fail closed.
    """
    expected = _number(expected_full)
    if expected is None or expected <= 0 or not isinstance(payload, dict):
        return None
    data = payload.get("sheet_datas")
    if not isinstance(data, dict):
        return None
    record = data.get("userAnswerRecordDTO")
    if not isinstance(record, dict):
        return None
    details = record.get("answerRecordDetails")
    if not isinstance(details, list) or not details:
        return None
    scores, maxima, seen = [], [], set()
    for item in details:
        if not isinstance(item, dict):
            return None
        title = str(item.get("dispTitle", ""))
        if not title.isdecimal():
            return None
        key = int(title)
        if key <= 0 or key in seen:
            return None
        seen.add(key)
        score, full = _number(item.get("score")), _number(item.get("standardScore"))
        if score is None or full is None or not 0 <= score <= full or full <= 0:
            return None
        scores.append(score)
        maxima.append(full)
    if not math.isclose(sum(maxima), expected, rel_tol=0, abs_tol=1e-6):
        return None
    return FallbackScore(sum(scores), expected, "答题卡计算")


def get_fallback_score(account, exam_id: str, paper_id: str, expected_full=None) -> FallbackScore | None:
    """Fetch exact sheet: explicit total first, then complete question total."""
    payload = account.get_sheet_payload(exam_id, paper_id)
    if not payload:
        return None
    return extract_total_score(payload) or extract_computed_score(payload, expected_full)
