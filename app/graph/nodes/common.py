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
        r"需求明确要求['‘“\"]([^'’”\"]{2,80})['’”\"]功能",
        r"未见([^，。；\n]{2,80})相关任务",
        r"未见([^，。；\n]{2,80})开发任务",
        r"未明确包含([^，。；\n]{2,80})逻辑",
    ]
    text = _normalize_text(issue)
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            phrase = _normalize_text(m.group(1))
            phrase = re.sub(r"^的", "", phrase).strip()
            phrase = phrase.strip("'\"‘’“”`")
            phrase = re.sub(r"[（(].*?[)）]$", "", phrase).strip()
            phrase = re.sub(r"(相关任务|开发任务|任务)$", "", phrase).strip()
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


def _tokenize_text(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_\-]{2,}|[\u4e00-\u9fff]{2,}", _normalize_text(text))


_COVERAGE_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    ("数据保留", "保留策略", "生命周期", "归档", "冷热", "容量", "存储规划", "备份恢复"),
    ("性能验证", "性能测试", "压测", "负载", "容量模型", "基准", "回归检测", "响应时间", "延迟"),
    ("监控告警", "监控", "告警规则", "指标采集", "日志追踪", "链路追踪", "可观测"),
    ("故障切换", "故障恢复", "高可用", "可用性", "备份恢复", "容灾", "演练"),
    ("灰度发布", "回滚", "发布策略", "变更验证", "流量切换"),
    ("权限", "访问控制", "RBAC", "隔离", "鉴权", "越权", "合规"),
    ("审计", "日志", "留痕", "追踪", "回溯"),
    ("依赖", "顺序", "前置", "状态机", "事件", "触发", "闭环"),
    ("并发", "冲突", "竞态", "锁", "事务", "唯一索引", "唯一约束", "组合索引", "幂等", "重复提交"),
    ("移动端", "移动", "App", "功能边界", "配置类操作", "路由守卫"),
)


def _alias_group_hits(text: str) -> set[int]:
    normalized = _normalize_text(text).lower()
    hits: set[int] = set()
    for idx, group in enumerate(_COVERAGE_ALIAS_GROUPS):
        if any(marker.lower() in normalized for marker in group):
            hits.add(idx)
    return hits


def _is_issue_covered_by_task(issue: str, task_text: str) -> bool:
    issue_groups = _alias_group_hits(issue)
    if issue_groups:
        task_groups = _alias_group_hits(task_text)
        shared = issue_groups & task_groups
        if len(shared) >= min(2, len(issue_groups)):
            return True
        if shared and any(marker in issue for marker in ("缺失", "未覆盖", "无", "缺少")):
            return True

    terms = _extract_issue_terms(issue)
    if not terms:
        return False
    threshold = min(2, len(terms))
    return sum(1 for term in terms if term in task_text) >= threshold


def _extract_issue_focus(issue: str) -> tuple[str, float]:
    phrase = _extract_issue_focus_phrase(issue)
    if phrase:
        return phrase, 0.9

    terms = _extract_issue_terms(issue, max_terms=3)
    if terms:
        return " ".join(terms[:2]), 0.6
    return "", 0.4


def _build_evidence_sources(
    tasks: list[dict[str, Any]],
    prompt_pack: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    task_titles = " ".join(str(item.get("title", "")) for item in (tasks or []))
    task_descriptions = " ".join(
        str(item.get("description", "")) for item in (tasks or [])
    )
    depends_on = " ".join(
        " ".join(str(dep) for dep in (item.get("depends_on", []) or []))
        for item in (tasks or [])
    )
    prompts = prompt_pack or []
    prompt_task_titles = " ".join(str(item.get("task_title", "")) for item in prompts)
    prompt_content = " ".join(
        f"{item.get('coding_prompt', '')} {item.get('test_prompt', '')}" for item in prompts
    )
    return {
        "task_title": _normalize_text(task_titles),
        "task_description": _normalize_text(task_descriptions),
        "prompt_task_title": _normalize_text(prompt_task_titles),
        "prompt_content": _normalize_text(prompt_content),
        "depends_on": _normalize_text(depends_on),
    }


def _source_hit(
    capability: str,
    issue_terms: list[str],
    source_text: str,
) -> bool:
    if not source_text:
        return False
    if capability and capability in source_text:
        return True
    if not issue_terms:
        return False
    threshold = min(2, len(issue_terms))
    return sum(1 for term in issue_terms if term in source_text) >= threshold


def analyze_blocking_issue_coverage(
    tasks: list[dict[str, Any]],
    blocking_issues: list[str],
    *,
    prompt_pack: list[dict[str, Any]] | None = None,
    min_evidence_hits: int = 2,
    min_confidence: float = 0.65,
    blocking_confidence: float = 0.75,
) -> dict[str, Any]:
    sources = _build_evidence_sources(tasks, prompt_pack=prompt_pack)
    source_weights = {
        "task_title": 0.30,
        "task_description": 0.22,
        "prompt_task_title": 0.20,
        "prompt_content": 0.18,
        "depends_on": 0.10,
    }

    uncovered: list[str] = []
    downgraded: list[str] = []
    diagnostics: list[dict[str, Any]] = []

    for issue in blocking_issues:
        issue_text = str(issue)
        capability, parse_confidence = _extract_issue_focus(issue_text)
        issue_terms = _extract_issue_terms(issue_text, max_terms=5)
        if capability:
            issue_terms = list(dict.fromkeys(_tokenize_text(capability) + issue_terms))

        matched_sources: list[str] = []
        for source_name, source_text in sources.items():
            if _source_hit(capability, issue_terms, source_text):
                matched_sources.append(source_name)

        evidence_hits = len(matched_sources)
        coverage_confidence = sum(source_weights[name] for name in matched_sources)
        is_covered = (
            evidence_hits >= max(1, int(min_evidence_hits))
            and coverage_confidence >= float(min_confidence)
        )

        missing_confidence = parse_confidence * max(0.2, 1.0 - coverage_confidence)
        if is_covered:
            decision = "covered"
        elif missing_confidence >= float(blocking_confidence):
            decision = "blocking_uncovered"
            uncovered.append(issue_text)
        else:
            decision = "downgraded_uncovered"
            downgraded.append(issue_text)

        diagnostics.append(
            {
                "issue_text": issue_text,
                "missing_capability": capability,
                "issue_terms": issue_terms[:6],
                "evidence_checked": list(sources.keys()),
                "matched_evidence": matched_sources,
                "evidence_hits": evidence_hits,
                "coverage_confidence": round(coverage_confidence, 3),
                "missing_confidence": round(missing_confidence, 3),
                "is_blocking": decision == "blocking_uncovered",
                "decision": decision,
                "why_not_matched": ""
                if matched_sources
                else "no sufficient cross-source evidence",
            }
        )

    return {
        "uncovered": uncovered,
        "downgraded": downgraded,
        "diagnostics": diagnostics,
    }


def find_uncovered_blocking_issues(
    tasks: list[dict[str, Any]],
    blocking_issues: list[str],
) -> list[str]:
    analysis = analyze_blocking_issue_coverage(
        tasks,
        blocking_issues,
        prompt_pack=None,
        min_evidence_hits=1,
        min_confidence=0.5,
        blocking_confidence=0.5,
    )
    return [str(item) for item in (analysis.get("uncovered", []) or [])]
