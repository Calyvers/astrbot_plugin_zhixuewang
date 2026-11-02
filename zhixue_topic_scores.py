"""逐题得分（小分）表数据整理。

数据来源与 /zx sheet 相同：checksheet 接口的 sheetDatas.userAnswerRecordDTO。
`answerRecordDetails` 每题带 topicNumber / dispTitle / score / standardScore，
按卷面题号排序后切成每行 per_row 题，超出自动换行。

服务端只有启用分步批改时才下发 stepDatas / stepRecords；此时 subTopics 的
stepRecords 会被 build_score_map 收集，本模块保留在 cell["steps"] 里，
当前表格仍按题级展示，避免把缺失的小问数据当成 0 分。
"""

from __future__ import annotations

import re
from typing import Any

DEFAULT_PER_ROW = 8


def format_number(value: Any) -> str:
    """13.0 -> '13'，13.5 -> '13.5'，None -> '—'。"""
    if value is None:
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if num.is_integer():
        return str(int(num))
    return f"{num:g}"


def _sort_key(item: dict) -> tuple:
    title = str(item.get("disp_title") or "")
    if title.isdigit():
        return (0, int(title), "")
    return (1, 0, title)


def build_subject_rows(score_map: dict, per_row: int = DEFAULT_PER_ROW) -> list[list[dict]]:
    """把 build_score_map 的结果排成 [[cell, ...], ...]，每个内层列表是一行。"""
    if per_row < 1:
        raise ValueError("per_row 必须大于 0")
    items = [it for it in score_map.values() if it]
    items.sort(key=_sort_key)

    cells: list[dict] = []
    for it in items:
        score = it.get("score")
        full = it.get("standard_score")
        lost = False
        if score is not None and full is not None:
            try:
                lost = float(score) < float(full)
            except (TypeError, ValueError):
                lost = False
        cells.append({
            "no": str(it.get("disp_title") or ""),
            "score": format_number(score),
            "full": format_number(full),
            "lost": lost,
            "steps": it.get("steps") or [],
        })
    rows = []
    for i in range(0, len(cells), per_row):
        chunk = cells[i:i + per_row]
        # 补空格子，保证每行等宽（table-layout:fixed），末行不拉伸
        chunk += [{"no": "", "score": "", "full": "", "lost": False,
                   "empty": True, "steps": []} for _ in range(per_row - len(chunk))]
        rows.append(chunk)
    return rows


def collect_topic_scores(account, exam, papers: list[dict],
                         per_row: int = DEFAULT_PER_ROW,
                         subject_name: str | None = None) -> list[dict]:
    """同步拉取各科答题卡并整理为逐题得分结构（调用方负责放线程池）。"""
    from .answer_sheet import build_score_map

    if subject_name:
        matched = [p for p in papers if subject_name.casefold() in str(p.get("subject_name", "")).casefold()]
        if not matched:
            names = "、".join(p["subject_name"] for p in papers) or "无"
            raise ValueError(f"未找到「{subject_name}」，该考试包含：{names}")
        papers = matched

    subjects: list[dict] = []
    for p in papers:
        if p.get("subject_code") == "99":
            continue
        payload = None
        try:
            payload = account.get_sheet_payload(exam.id, p["paper_id"])
        except Exception:
            payload = None

        rows: list[list[dict]] = []
        score = p.get("score")
        standard = p.get("standard_score")
        labels = p.get("status_labels") or []
        if payload:
            sheet_datas = payload.get("sheet_datas")
            if isinstance(sheet_datas, dict) and sheet_datas:
                score_map = build_score_map(sheet_datas, payload.get("step_datas"))
                rows = build_subject_rows(score_map, per_row=per_row)
            elif any("未扫描" in str(label) for label in labels):
                # Only an explicit unpublished/unscanned marker makes report 0 a placeholder.
                score = standard = None
            got = [it.get("score") for row in rows for it in row
                   if not it.get("empty") and it.get("score") not in (None, "—")]
            full = [it.get("full") for row in rows for it in row
                    if not it.get("empty") and it.get("full") not in (None, "—")]
            cell_count = sum(1 for row in rows for it in row if not it.get("empty"))
            # Only derive totals when every topic has the corresponding value;
            # partial sheets must not be presented as a complete total.
            if score is None and got and len(got) == cell_count:
                score = sum(float(x) for x in got)
            if standard is None and full and len(full) == cell_count:
                standard = sum(float(x) for x in full)
        elif (any("未扫描" in str(label) for label in labels)
              or (payload and (not isinstance(payload.get("sheet_datas"), dict)
                               or not payload.get("sheet_datas")))):
            # 明确未扫描或答题卡结构异常时，报告接口的 0 只是占位。
            score = standard = None

        subjects.append({
            "subject": p["subject_name"],
            "score": format_number(score),
            "standard_score": format_number(standard),
            "available": bool(rows),
            "note": "、".join(str(x) for x in labels),
            "rows": rows,
        })
    return subjects


def format_topic_scores_text(student: str, exam_name: str, subjects: list[dict],
                             per_row: int = DEFAULT_PER_ROW) -> str:
    """纯文本降级：每科两行（题号 / 得分），按 per_row 换行。"""
    if per_row < 1:
        raise ValueError("per_row 必须大于 0")
    lines = [f"{student} · 逐题得分", exam_name]
    for s in subjects:
        if not s["available"]:
            note = f"{s['note']}，" if s.get("note") else ""
            report = ""
            if s.get("score") not in (None, "", "—") or s.get("standard_score") not in (None, "", "—"):
                report = f"报告分 {s.get('score', '—')}/{s.get('standard_score', '—')}；"
            lines.append(f"\n{s['subject']}  {report}{note}暂无小分数据")
            continue
        lines.append(f"\n{s['subject']}  {s['score']}/{s['standard_score']}")
        cells = [c for row in s["rows"] for c in row if not c.get("empty")]
        for i in range(0, len(cells), per_row):
            chunk = cells[i:i + per_row]
            lines.append(" ".join(f"{c['no']}:{c['score']}" for c in chunk))
    return "\n".join(lines)


def parse_score_args(text: str) -> tuple[str | None, str | None]:
    """解析 `/zx score [-s 学科] [考试序号/名称]`，返回 (subject, exam_param)。"""
    text = (text or "").strip()
    subject = None
    m = re.search(r"(?:^|\s)(?:-s|--subject)(?:\s+|$)", text)
    if m:
        tail = text[m.end():]
        # -s/--subject consumes one quoted token (spaces supported) or one
        # unquoted token; any following text remains the exam argument.
        if tail[:1] in ("'", '\"'):
            quote = tail[0]
            end = tail.find(quote, 1)
            if end < 0:
                raise ValueError("学科名称引号未闭合")
            subject = tail[1:end].strip()
            rest = tail[end + 1:].strip()
        else:
            # Whitespace separates an optional exam argument; support spaces/tabs.
            parts = tail.split(None, 1)
            subject = parts[0] if parts else ""
            rest = parts[1] if len(parts) > 1 else ""
        if not subject:
            raise ValueError("请提供学科名称，例如：-s 数学")
        prefix = text[:m.start()].strip()
        text = " ".join(x for x in (prefix, rest) if x).strip()
    return subject or None, (text or None)
