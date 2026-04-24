import json
import re
from typing import Any


def extract_structured_response(result: dict):
    structured = result.get("structured_response")
    if structured is None:
        raise ValueError("Agent did not return structured_response")
    return structured


def compact_json(data: Any, max_chars: int = 3000) -> str:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "...(truncated)"


def summarize_task_breakdown(tasks: list[dict[str, Any]], max_items: int = 12) -> str:
    lines = []
    for item in tasks[:max_items]:
        title = item.get("title", "")
        priority = item.get("priority", "")
        owner = item.get("owner_role", "")
        deps = item.get("depends_on", [])
        dep_titles = ", ".join([str(dep) for dep in deps[:2]]) if deps else "-"
        lines.append(
            f"- {title} | priority={priority} | owner={owner} | deps={len(deps)} | dep_titles={dep_titles}"
        )
    if len(tasks) > max_items:
        lines.append(f"... and {len(tasks) - max_items} more tasks")
    return "\n".join(lines)


def summarize_prompt_pack(prompt_pack: list[dict[str, Any]], max_items: int = 8) -> str:
    lines = []
    for item in prompt_pack[:max_items]:
        task_title = item.get("task_title", "")
        coding_prompt = item.get("coding_prompt", "")
        test_prompt = item.get("test_prompt", "")
        lines.append(
            f"- {task_title} | coding_len={len(coding_prompt)} | test_len={len(test_prompt)}"
        )
    if len(prompt_pack) > max_items:
        lines.append(f"... and {len(prompt_pack) - max_items} more prompt items")
    return "\n".join(lines)


def summarize_review_feedback(
    review_report: dict[str, Any],
    max_issues: int = 8,
    max_suggestions: int = 8,
) -> str:
    issues = review_report.get("issues", []) if isinstance(review_report, dict) else []
    suggestions = (
        review_report.get("suggestions", []) if isinstance(review_report, dict) else []
    )
    lines: list[str] = []
    if issues:
        lines.append("评审问题(issues):")
        for item in issues[:max_issues]:
            lines.append(f"- {item}")
        if len(issues) > max_issues:
            lines.append(f"... and {len(issues) - max_issues} more issues")
    if suggestions:
        lines.append("评审建议(suggestions):")
        for item in suggestions[:max_suggestions]:
            lines.append(f"- {item}")
        if len(suggestions) > max_suggestions:
            lines.append(f"... and {len(suggestions) - max_suggestions} more suggestions")
    return "\n".join(lines)


def summarize_key_list(items: list[Any], max_items: int = 8, max_chars: int = 1200) -> str:
    compact_items = [str(item) for item in (items or [])[:max_items]]
    return compact_json(compact_items, max_chars=max_chars)


def extract_blocking_issues(review_report: dict[str, Any], max_items: int = 8) -> list[str]:
    if not isinstance(review_report, dict):
        return []
    issues = [str(i) for i in (review_report.get("issues", []) or [])]
    if not issues:
        return []

    blocking_markers = ["关键", "缺失", "阻塞", "无法", "失败", "风险", "未覆盖", "must"]
    selected = [i for i in issues if any(m in i for m in blocking_markers)]
    if not selected:
        selected = issues
    return selected[:max_items]


def _normalize_text(text: str) -> str:
    text = re.sub(r"^【[^】]+】", "", text).strip()
    text = text.replace("（", "(").replace("）", ")")
    return text


def _extract_issue_focus_phrase(issue: str) -> str | None:
    patterns = [
        r"缺少([^，。；\n]{2,80})任务",
        r"未包含([^，。；\n]{2,80})任务",
        r"新增任务[:：]\s*([^，。；\n]{2,80})",
    ]
    text = _normalize_text(issue)
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            phrase = _normalize_text(m.group(1))
            phrase = re.sub(r"^的", "", phrase).strip()
            return phrase if phrase else None
    return None


def _extract_issue_terms(issue: str, max_terms: int = 4) -> list[str]:
    text = _normalize_text(issue)
    tokens = re.findall(r"[A-Za-z0-9_\-]{3,}|[\u4e00-\u9fff]{2,}", text)
    stop_words = {
        "关键功能",
        "缺失",
        "任务清单",
        "任务",
        "功能",
        "机制",
        "方案",
        "实现",
        "支持",
        "导致",
        "影响",
        "当前",
        "系统",
        "流程",
        "上线",
    }
    terms: list[str] = []
    for token in tokens:
        if token in stop_words:
            continue
        if token not in terms:
            terms.append(token)
        if len(terms) >= max_terms:
            break
    return terms


def find_uncovered_blocking_issues(
    tasks: list[dict[str, Any]],
    blocking_issues: list[str],
) -> list[str]:
    task_texts = [
        _normalize_text(f"{item.get('title', '')} {item.get('description', '')}")
        for item in (tasks or [])
    ]
    uncovered: list[str] = []
    for issue in blocking_issues:
        focus_phrase = _extract_issue_focus_phrase(issue)
        if focus_phrase:
            if any(focus_phrase in t for t in task_texts):
                continue
            uncovered.append(issue)
            continue

        terms = _extract_issue_terms(issue)
        if not terms:
            # Conservatively mark as uncovered when no usable signal can be extracted.
            uncovered.append(issue)
            continue
        threshold = min(2, len(terms))
        matched = False
        for text in task_texts:
            score = sum(1 for term in terms if term in text)
            if score >= threshold:
                matched = True
                break
        if not matched:
            uncovered.append(issue)
    return uncovered
