"""Production ranking query module using the plugin account/API client."""

def valid_rank(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return int(n) if n > 0 and n.is_integer() else None
    except (TypeError, ValueError, OverflowError):
        return None


def parse_ranks_args(text):
    parts = (text or "").strip().split(maxsplit=1)
    if parts and parts[0].lower() == "all":
        return (parts[1].strip() if len(parts) > 1 else None), True
    return ((text or "").strip() or None), False


def format_ranks_table(user_name, exam_name, subjects):
    lines = [f"{user_name} · 排名", exam_name, "科目 | 班级排名 | 年级排名"]
    for s in subjects:
        label = "、".join(s.get("status_labels") or [])
        lines.append(f"{s['subject']} | {s.get('class_rank') or '无排名'} | {s.get('grade_rank') or '无排名'}" + (f"（{label}）" if label else ""))
    if not subjects:
        lines.append("该考试暂无科目排名数据")
    return "\n".join(lines)


async def get_ranks(manager, user_id: str, config_users: list, exam_param: str = None, show_all: bool = False):
    """Query ranking data through the production account/API client."""
    account, _ = await manager.get_account(user_id, config_users)
    exam = manager._resolve_exam_or_latest(account, exam_param)
    report = account.get_rank_report(exam)
    subjects = []
    seen = set()
    for paper in (report.get("paperList") or []) + (report.get("absentPaperList") or []):
        key = paper.get("paperId") or paper.get("subjectCode") or paper.get("subjectName")
        if key in seen:
            continue
        seen.add(key)
        subjects.append({
            "subject": paper.get("subjectName", "未知科目"),
            "class_rank": valid_rank(paper.get("clazzRank")),
            "grade_rank": valid_rank(paper.get("gradeRank")),
            "status_labels": [x["labelName"] for x in (paper.get("subjectLabels") or [])
                              if isinstance(x, dict) and isinstance(x.get("labelName"), str)],
        })
    total = report.get("totalScore")
    if isinstance(total, dict) and (valid_rank(total.get("clazzRank")) or valid_rank(total.get("gradeRank"))):
        subjects.append({"subject": total.get("subjectName", "总分"),
                         "class_rank": valid_rank(total.get("clazzRank")),
                         "grade_rank": valid_rank(total.get("gradeRank")),
                         "status_labels": []})
    return account.name, {"name": exam.name, "id": exam.id}, subjects
