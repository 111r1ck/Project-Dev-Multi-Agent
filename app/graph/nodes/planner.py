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
from app.services.planning_guardrails import (
    align_dependency_priorities,
    apply_assumption_pack_tasks,
    ensure_architecture_module_tasks,
    ensure_guardrail_tasks,
    ensure_risk_mitigation_tasks,
)
from app.services.task_dependency_resolver import resolve_task_dependencies
from app.services.task_dependency_resolver import break_dependency_cycles
from app.services.task_dependency_resolver import fix_dependency_direction_anti_patterns


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
        r"补充([^，。；\n]{2,80})任务",
        r"功能缺失[:：][^'’”\"\n]*['‘“\"]([^'’”\"]{2,80})['’”\"]功能",
        r"需求明确要求([^，。；\n]{2,80})功能",
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
    *,
    max_new_tasks: int | None = None,
) -> list[dict]:
    existing_text = " ".join(
        [f"{item.get('title', '')} {item.get('description', '')}" for item in tasks]
    )
    normalized_tasks = list(tasks)
    candidates = _extract_missing_task_candidates(review_report)
    added = 0
    for title, source_text in candidates:
        if max_new_tasks is not None and added >= max_new_tasks:
            break
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
        added += 1
    return normalized_tasks


def _apply_review_task_updates(tasks: list[dict], review_report: dict) -> list[dict]:
    if not isinstance(review_report, dict):
        return tasks

    texts: list[str] = []
    texts.extend([str(item) for item in (review_report.get("issues", []) or [])])
    texts.extend([str(item) for item in (review_report.get("suggestions", []) or [])])
    if not texts:
        return tasks

    normalized_tasks = [dict(task) for task in tasks]
    title_to_task = {
        str(task.get("title", "")).strip(): task for task in normalized_tasks if task.get("title")
    }
    update_patterns = [
        r"在['‘“\"]?([^'’”\"]+?)['’”\"]?任务中添加[^：:]*[：:]\s*['‘“\"]?([^'’”\"。；\n]+)",
        r"为['‘“\"]?([^'’”\"]+?)['’”\"]?任务补充[^：:]*[：:]\s*['‘“\"]?([^'’”\"。；\n]+)",
    ]
    for text in texts:
        normalized_text = _normalize_text(text)
        for pattern in update_patterns:
            for title, addition in re.findall(pattern, normalized_text):
                task = title_to_task.get(title.strip())
                addition = addition.strip()
                if not task or not addition:
                    continue
                description = str(task.get("description", "")).strip()
                if addition not in description:
                    task["description"] = f"{description} {addition}".strip()
    return normalized_tasks


def _priority_rank(priority: str) -> int:
    normalized = str(priority or "").strip().upper()
    mapping = {
        "最高": 0,
        "高": 0,
        "P0": 0,
        "中": 1,
        "P1": 1,
        "低": 2,
        "P2": 2,
        "P3": 3,
    }
    return mapping.get(normalized, 2)


def _task_budget_from_complexity(complexity: str) -> int:
    normalized = str(complexity or "").strip().lower()
    if normalized in {"low", "simple", "s", "小", "低"}:
        return 12
    if normalized in {"high", "复杂", "高", "h"}:
        return 24
    return 18


def _extract_blocking_terms(review_report: dict, limit: int = 8) -> set[str]:
    if not isinstance(review_report, dict):
        return set()
    issues = [str(item) for item in (review_report.get("issues", []) or [])]
    terms: list[str] = []
    for issue in issues:
        tokens = re.findall(r"[A-Za-z0-9_\-]{3,}|[\u4e00-\u9fff]{2,}", issue)
        for token in tokens:
            if token not in terms:
                terms.append(token)
            if len(terms) >= limit:
                return set(terms)
    return set(terms)


def _trim_tasks_by_budget(
    tasks: list[dict],
    *,
    budget: int,
    blocking_terms: set[str],
) -> list[dict]:
    if budget <= 0 or len(tasks) <= budget:
        return list(tasks)

    normalized = [dict(task) for task in tasks]
    indexed = list(enumerate(normalized))
    assumption_anchor_titles = {
        "验证关键假设与替代方案",
        "落实受控假设的风险控制措施",
        "上线前确认清单与决策复核",
        "确认范围收缩与替代方案边界",
    }

    def _task_text(task: dict) -> str:
        return f"{task.get('title', '')} {task.get('description', '')}"

    must_keep_indices: set[int] = set()
    anchor_indices: set[int] = set()
    for idx, task in indexed:
        priority = _priority_rank(str(task.get("priority", "")))
        text = _task_text(task)
        title = str(task.get("title", "")).strip()
        if title in assumption_anchor_titles:
            must_keep_indices.add(idx)
            anchor_indices.add(idx)
            continue
        # Review backflow tasks should survive budget trimming,
        # otherwise we may lose just-added remediation items.
        if "基于评审回流补齐" in str(task.get("description", "")):
            must_keep_indices.add(idx)
            continue
        if priority == 0:
            must_keep_indices.add(idx)
            continue
        if blocking_terms and any(term in text for term in blocking_terms):
            must_keep_indices.add(idx)

    sorted_indices = sorted(
        range(len(normalized)),
        key=lambda i: (
            0 if i in anchor_indices else 1,
            _priority_rank(str(normalized[i].get("priority", ""))),
            i,
        ),
    )
    effective_budget = max(int(budget), len(must_keep_indices))
    selected_indices: list[int] = []
    for idx in sorted_indices:
        if idx in must_keep_indices:
            selected_indices.append(idx)
    for idx in sorted_indices:
        if idx in selected_indices:
            continue
        selected_indices.append(idx)
        if len(selected_indices) >= effective_budget:
            break

    selected_indices = selected_indices[:effective_budget]
    selected = [normalized[idx] for idx in sorted(selected_indices)]
    selected_titles = {
        str(item.get("title", "")).strip() for item in selected if str(item.get("title", "")).strip()
    }
    for task in selected:
        deps = [str(dep).strip() for dep in (task.get("depends_on", []) or [])]
        task["depends_on"] = [dep for dep in deps if dep and dep in selected_titles]
    return selected


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
        "依赖约束：depends_on 只能指向前置能力任务，禁止形成循环依赖。\n"
        "禁止将测试/压测/集成/验收任务作为基础开发或基础设施任务的前置依赖。\n"
        f"需求摘要: {req.get('summary', '')}\n"
        f"关键约束: {summarize_key_list(req.get('constraints', []), max_items=10, max_chars=1200)}\n"
        f"关键风险: {summarize_key_list(fea.get('risks', []), max_items=8, max_chars=1000)}\n"
        f"架构风格: {arch.get('architecture_style', '')}\n"
        f"后端技术: {compact_json((arch.get('backend', []) or [])[:8], max_chars=600)}\n"
        f"前端技术: {compact_json((arch.get('frontend', []) or [])[:8], max_chars=600)}\n"
        f"核心模块: {compact_json(modules, max_chars=1600)}\n"
        f"人工确认决策: {compact_json(state.get('project_decisions', {}), max_chars=1600)}\n"
        f"受控假设包: {compact_json(state.get('assumption_pack', {}), max_chars=1600)}"
    )

    review_rounds = int(state.get("review_rounds", 0) or 0)
    review_report = state.get("review_report", {}) or {}
    is_rework_round = review_rounds > 0 and not bool(review_report.get("passed"))
    previous_tasks_count = len(state.get("task_breakdown", []) or [])
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
    review_report_for_constraints = review_report
    if is_rework_round:
        review_report_for_constraints = {
            "issues": review_report.get("issues", []),
            "suggestions": [],
        }
    signals = classify_constraints(
        requirement_doc=req,
        architecture_plan=arch,
        project_decisions=state.get("project_decisions", {}),
        review_report=review_report_for_constraints,
    )
    tasks = ensure_guardrail_tasks(tasks, signals)
    tasks = ensure_architecture_module_tasks(tasks, arch)
    tasks = apply_assumption_pack_tasks(tasks, state.get("assumption_pack", {}))
    tasks = ensure_risk_mitigation_tasks(tasks, fea, review_report)
    tasks = _ensure_missing_tasks_from_review(
        tasks,
        review_report,
        max_new_tasks=3 if is_rework_round else 6,
    )
    tasks = _apply_review_task_updates(tasks, review_report)
    tasks = resolve_task_dependencies(tasks)
    tasks, direction_fix_diagnostics = fix_dependency_direction_anti_patterns(tasks)
    tasks, dependency_diagnostics = break_dependency_cycles(tasks)
    tasks = align_dependency_priorities(tasks)
    budget = _task_budget_from_complexity(fea.get("complexity", ""))
    if is_rework_round and previous_tasks_count > 0:
        budget = min(budget, previous_tasks_count)
    tasks = _trim_tasks_by_budget(
        tasks,
        budget=budget,
        blocking_terms=_extract_blocking_terms(review_report),
    )

    return {
        **state,
        "task_breakdown": tasks,
        "task_dependency_diagnostics": {
            **(dependency_diagnostics or {}),
            **(direction_fix_diagnostics or {}),
        },
        "next_step": "prompt_builder",
    }
