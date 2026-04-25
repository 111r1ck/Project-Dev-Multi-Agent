import re

from app.agents.planner_agent import build_planner_agent
from app.graph.nodes.common import (
    compact_json,
    extract_structured_response,
    summarize_key_list,
    summarize_review_feedback,
)
from app.graph.state import ProjectState
from app.services.constraint_classifier import classify_constraints
from app.services.planning_guardrails import ensure_guardrail_tasks
from app.services.task_dependency_resolver import resolve_task_dependencies


def _normalize_text(text: str) -> str:
    text = re.sub(r"^【[^】]+】", "", text).strip()
    text = text.replace("（", "(").replace("）", ")")
    return text


def _extract_missing_task_candidates(review_report: dict) -> list[tuple[str, str]]:
    """
    Extract candidate missing task titles from reviewer issues/suggestions.
    This keeps the mechanism domain-agnostic and driven by current review feedback.
    """
    texts = []
    if isinstance(review_report, dict):
        texts.extend(review_report.get("issues", []) or [])
        texts.extend(review_report.get("suggestions", []) or [])

    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    patterns = [
        r"新增任务[:：]\s*([^，。；\n]+)",
        r"缺少([^，。；\n]{2,60})任务",
        r"未包含([^，。；\n]{2,60})任务",
        r"未包含([^，。；\n]{2,60})",
    ]

    for raw in texts:
        text = _normalize_text(str(raw))
        for pattern in patterns:
            for match in re.findall(pattern, text):
                title = _normalize_text(match)
                title = re.sub(r"^的", "", title).strip()
                if not title:
                    continue
                if not title.endswith("任务"):
                    title = f"{title}任务"
                if title in seen:
                    continue
                seen.add(title)
                candidates.append((title, text))
    return candidates


def _infer_priority_from_text(text: str, default: str = "P1") -> str:
    normalized = text.upper()
    match = re.search(r"\bP([0-3])\b", normalized)
    if match:
        return f"P{match.group(1)}"

    if re.search(r"优先级\s*[:=：]\s*高", text):
        return "P0"
    if re.search(r"优先级\s*[:=：]\s*中", text):
        return "P1"
    if re.search(r"优先级\s*[:=：]\s*低", text):
        return "P2"

    if re.search(r"\b(CRITICAL|BLOCKER)\b", normalized):
        return "P0"
    if re.search(r"\bHIGH\b", normalized):
        return "P0"
    if re.search(r"\bMEDIUM\b", normalized):
        return "P1"
    if re.search(r"\bLOW\b", normalized):
        return "P2"
    return default


def _infer_owner_from_text(text: str, default: str = "后端开发工程师") -> str:
    patterns = [
        r"owner\s*[:=：]\s*([^，。；\n]+)",
        r"负责人\s*[:=：]\s*([^，。；\n]+)",
        r"责任人\s*[:=：]\s*([^，。；\n]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            owner = m.group(1).strip()
            if owner:
                return owner
    return default


def _ensure_missing_tasks_from_review(
    tasks: list[dict],
    review_report: dict,
) -> list[dict]:
    existing_text = " ".join(
        [f"{item.get('title', '')} {item.get('description', '')}" for item in tasks]
    )
    normalized_tasks = list(tasks)
    candidates = _extract_missing_task_candidates(review_report)
    for title, source_text in candidates:
        if title in existing_text:
            continue
        task = {
            "title": title,
            "description": f"基于评审回流补齐：实现{title}并完成联调、异常处理与验收。",
            "priority": _infer_priority_from_text(source_text),
            "depends_on": [],
            "owner_role": _infer_owner_from_text(source_text),
        }
        normalized_tasks.append(task)
        existing_text += f" {task['title']} {task['description']}"
    return normalized_tasks


def planner_node(state: ProjectState) -> ProjectState:
    req = state["requirement_doc"]
    fea = state.get("feasibility_report", {}) or {}
    arch = state["architecture_plan"]
    modules = []
    for module in arch.get("modules", [])[:10]:
        name = module.get("name", "")
        responsibilities = module.get("responsibilities", [])
        modules.append(
            {"name": name, "responsibilities": responsibilities[:3]}
        )
    compact_context = (
        "请基于以下摘要拆分任务。\n"
        f"需求摘要: {req.get('summary', '')}\n"
        f"关键约束: {summarize_key_list(req.get('constraints', []), max_items=10, max_chars=1200)}\n"
        f"关键风险: {summarize_key_list(fea.get('risks', []), max_items=8, max_chars=1000)}\n"
        f"架构风格: {arch.get('architecture_style', '')}\n"
        f"后端技术: {compact_json((arch.get('backend', []) or [])[:8], max_chars=600)}\n"
        f"前端技术: {compact_json((arch.get('frontend', []) or [])[:8], max_chars=600)}\n"
        f"核心模块: {compact_json(modules, max_chars=1600)}\n"
        f"人工确认决策: {compact_json(state.get('project_decisions', {}), max_chars=1600)}"
    )

    review_rounds = int(state.get("review_rounds", 0) or 0)
    review_report = state.get("review_report", {}) or {}
    is_rework_round = review_rounds > 0 and not bool(review_report.get("passed"))
    if is_rework_round:
        review_feedback = summarize_review_feedback(
            review_report, max_issues=6, max_suggestions=6
        )
        compact_context += (
            "\n\n[回流修复模式]\n"
            "上一轮评审未通过。请基于下述评审问题与建议，对任务拆解进行逐条修复闭环：\n"
            f"{review_feedback}\n"
            "要求：\n"
            "1) 任务必须覆盖上述issues，避免遗漏。\n"
            "2) 为修复项补充必要的任务与依赖关系。\n"
            "3) 对明显不合理或冲突的任务进行替换或重写。"
        )

    agent = build_planner_agent()
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": compact_context,
                }
            ]
        }
    )
    structured = extract_structured_response(result)
    tasks = [task.model_dump() for task in structured.tasks]
    signals = classify_constraints(
        requirement_doc=req,
        architecture_plan=arch,
        project_decisions=state.get("project_decisions", {}),
        review_report=review_report,
    )
    tasks = ensure_guardrail_tasks(tasks, signals)
    tasks = _ensure_missing_tasks_from_review(tasks, review_report)
    tasks = resolve_task_dependencies(tasks)

    return {
        **state,
        "task_breakdown": tasks,
        "next_step": "prompt_builder",
    }
