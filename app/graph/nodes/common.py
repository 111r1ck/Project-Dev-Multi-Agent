import json
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
        lines.append(
            f"- {title} | priority={priority} | owner={owner} | deps={len(deps)}"
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
