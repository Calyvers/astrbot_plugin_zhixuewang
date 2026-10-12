"""Opt-in trend interpolation; never an authoritative reported score.

The request function returns RAW result: its response must be checked for the
exact exam/paper and adapted to verified score-percentage interval bounds.
Do not substitute rank percentiles, mastery tips or UI pixel positions.
This module is deliberately not wired into get_marks pending live validation.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

TREND_URL = 'https://ali-bg.zhixue.com/zhixuebao/report/paper/getLevelTrend'


def _decimal(value):
    if isinstance(value, bool) or value is None:
        raise ValueError('missing or invalid numeric value')
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('invalid numeric value') from None
    if not number.is_finite():
        raise ValueError('non-finite value')
    return number


@dataclass(frozen=True)
class RateEstimate:
    exam_id: str
    paper_id: str
    subject_code: str
    rate_percent: Decimal
    raw_score: Decimal
    rounded_score: Decimal
    full_score: Decimal
    source: str = '趋势区间插值'
    estimated: bool = True


def estimate_score(*, exam_id, paper_id, subject_code, full_score,
                   score_level_type, lower_percent, upper_percent, offset,
                   verified_score_axis=False):
    """Consume VERIFIED normalized bounds, not unexamined server objects.

    Formula: [lower + offset / 100 * (upper - lower)] / 100 * full.
    'score' alone does not prove axis semantics; the adapter must verify them.
    Rounded score uses decimal ROUND_HALF_UP; raw score is always retained.
    """
    if not all(isinstance(v, str) and v.strip() for v in
               (exam_id, paper_id, subject_code)):
        raise ValueError('exact exam/paper/subject identity required')
    if score_level_type != 'score' or verified_score_axis is not True:
        raise ValueError('unverified score-percentage axis')
    low, high, position, full = map(_decimal,
        (lower_percent, upper_percent, offset, full_score))
    if not (0 <= low < high <= 100 and 0 <= position <= 100 and full > 0):
        raise ValueError('invalid interval, offset or full score')
    rate = low + position * (high - low) / 100
    raw = rate * full / 100
    return RateEstimate(exam_id, paper_id, subject_code, rate, raw,
                        raw.quantize(Decimal('1'), rounding=ROUND_HALF_UP), full)


def request_trend(session, *, headers, exam_id, paper_id,
                  start_school_year, end_school_year):
    """One read-only request using caller-authorized session; no secret reads.

    Does not log responses/headers or retry. Returned data is NOT a score.
    Caller must check response identity and interval semantics before estimation.
    """
    if not all((exam_id, paper_id, start_school_year, end_school_year)):
        raise ValueError('exam, paper and school year required')
    response = session.get(TREND_URL, params={
        'examId': exam_id, 'paperId': paper_id,
        'startSchoolYear': start_school_year, 'endSchoolYear': end_school_year,
        'pageIndex': 1, 'pageSize': 1,
    }, headers=headers, timeout=20)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get('errorCode') != 0:
        raise ValueError('trend API did not return success')
    result = payload.get('result')
    if not isinstance(result, dict) or not isinstance(result.get('list'), list) or not result['list']:
        raise ValueError('trend data unavailable')
    return result


# Only this percentage-axis profile has been cross-checked against real scores.
# A new axis must be explicitly validated, not silently treated as percentages.
_VERIFIED_AXIS = {
    'A等': (Decimal(85), Decimal(100)),
    'B等': (Decimal(70), Decimal(85)),
    'C等': (Decimal(60), Decimal(70)),
    'D等': (Decimal(40), Decimal(60)),
    'E等': (Decimal(0), Decimal(40)),
}


def parse_trend(result, *, exam_id, exam_name, paper_id, subject_code, full_score):
    """Adapt request_trend's result; fail closed on missing/ambiguous evidence.

    The caller must obtain paper_id, subject_code and full_score from the SAME
    report item. The trend has no subjectCode to independently verify that link.
    All returned groups must contain exactly one matching paper/exam record and
    agree on axis, level and offset. Group reference semantics are not assumed.
    Raises ValueError for unavailable/unsupported data; never substitutes zero.
    """
    if not isinstance(exam_name, str) or not exam_name.strip():
        raise ValueError('exact exam name required')
    if not isinstance(result, dict) or result.get('scoreLevelType') != 'score':
        raise ValueError('unsupported trend axis type')
    groups = result.get('list')
    if not isinstance(groups, list) or not groups:
        raise ValueError('trend groups unavailable')
    estimates, evidence = [], []
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError('invalid trend group')
        levels, data = group.get('levelList'), group.get('dataList')
        if not isinstance(levels, list) or not isinstance(data, list):
            raise ValueError('missing levels or records')
        axis = {}
        for level in levels:
            if not isinstance(level, dict):
                raise ValueError('invalid level')
            name = level.get('name')
            if not isinstance(name, str) or name in axis:
                raise ValueError('invalid or duplicate level name')
            axis[name] = (_decimal(level.get('lowBound')),
                          _decimal(level.get('upperBound')))
        if axis != _VERIFIED_AXIS:
            raise ValueError('unverified percentage-axis profile')
        if any(not isinstance(d, dict) for d in data):
            raise ValueError('invalid trend record')
        matches = [d for d in data if d.get('id') == paper_id]
        if len(matches) != 1 or matches[0].get('name') != exam_name:
            raise ValueError('missing, duplicate or mismatched paper/exam')
        bar = matches[0].get('improveBar')
        if not isinstance(bar, dict) or bar.get('show') is not True:
            raise ValueError('trend score is hidden or unavailable')
        level_name = bar.get('levelScale')
        if not isinstance(level_name, str) or level_name not in axis:
            raise ValueError('unknown score level')
        low, high = axis[level_name]
        offset = _decimal(bar.get('offset'))
        estimates.append(estimate_score(
            exam_id=exam_id, paper_id=paper_id, subject_code=subject_code,
            full_score=full_score, score_level_type='score', lower_percent=low,
            upper_percent=high, offset=offset, verified_score_axis=True))
        evidence.append((level_name, offset))
    if any(e != evidence[0] for e in evidence[1:]):
        raise ValueError('conflicting trend groups')
    return estimates[0]


def request_estimate(session, *, headers, exam_id, exam_name, paper_id,
                     subject_code, full_score, start_school_year, end_school_year):
    """Read-only request + strict adapter. Caller handles network/ValueError.

    No credentials are loaded or persisted here. Output remains an estimate,
    even for previously verified exams; fractional raw scores are retained.
    """
    result = request_trend(session, headers=headers, exam_id=exam_id,
                           paper_id=paper_id, start_school_year=start_school_year,
                           end_school_year=end_school_year)
    return parse_trend(result, exam_id=exam_id, exam_name=exam_name,
                       paper_id=paper_id, subject_code=subject_code,
                       full_score=full_score)
