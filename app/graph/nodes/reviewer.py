from app.agents.reviewer_agent import build_reviewer_agent
from app.config import settings
from app.graph.nodes.common import (
    extract_blocking_issues,
    extract_structured_response,
    find_uncovered_blocking_issues,
    summarize_key_list,
    summarize_prompt_pack,
    summarize_review_feedback,
    summarize_task_breakdown,
)
from app.graph.state import ProjectState
from app.services.reviewer_cache import load_cached_review, save_cached_review


def _apply_review_outcome(
    state: ProjectState,
    review_report: dict,
    passed: bool,
) -> ProjectState:
    review_rounds = int(state.get("review_rounds", 0))
    max_review_rounds = int(state.get("max_review_rounds", settings.review_max_rounds))

    if passed:
        return {
            **state,
            "review_report": review_report,
            "next_step": "finish",
        }

    next_review_rounds = review_rounds + 1
    if next_review_rounds >= max_review_rounds:
        errors = list(state.get("errors", []))
        errors.append(
            f"评审未通过，已达到最大复审轮次({max_review_rounds})，请根据review_report人工修正后再运行。"
        )
        return {
            **state,
            "review_report": review_report,
            "review_rounds": next_review_rounds,
            "errors": errors,
            "next_step": "finish",
        }

    return {
        **state,
        "review_report": review_report,
        "review_rounds": next_review_rounds,
        "next_step": "planner",
    }


def _build_reviewer_cache_payload(
    req: dict,
    fea: dict,
    arch: dict,
    tasks: list[dict],
    prompts: list[dict],
    previous_review: dict,
    review_rounds: int,
) -> dict:
    compact_tasks = [
        {
            "title": str(item.get("title", "")).strip(),
            "priority": str(item.get("priority", "")).strip(),
            "depends_on": [str(dep).strip() for dep in (item.get("depends_on", []) or [])],
        }
        for item in (tasks or [])
    ]
    compact_prompts = [
        {
            "task_title": str(item.get("task_title", "")).strip(),
            "coding_prompt": str(item.get("coding_prompt", "")).strip(),
            "test_prompt": str(item.get("test_prompt", "")).strip(),
        }
        for item in (prompts or [])
    ]
    return {
        "review_rounds": int(review_rounds),
        "requirement": {
            "summary": req.get("summary", ""),
            "constraints": req.get("constraints", []) or [],
        },
        "feasibility": {
            "feasible": fea.get("feasible"),
            "complexity": fea.get("complexity", ""),
            "risks": fea.get("risks", []) or [],
        },
        "architecture": {
            "style": arch.get("architecture_style", ""),
            "backend": arch.get("backend", []) or [],
            "frontend": arch.get("frontend", []) or [],
        },
        "tasks": compact_tasks,
        "prompts": compact_prompts,
        "previous_review": {
            "passed": bool(previous_review.get("passed")) if isinstance(previous_review, dict) else None,
            "issues": (previous_review.get("issues", []) if isinstance(previous_review, dict) else []) or [],
            "suggestions": (previous_review.get("suggestions", []) if isinstance(previous_review, dict) else []) or [],
        },
    }


def reviewer_node(state: ProjectState) -> ProjectState:
    req = state["requirement_doc"]
    fea = state["feasibility_report"]
    arch = state["architecture_plan"]
    tasks = state.get("task_breakdown", [])
    prompts = state.get("prompt_pack", [])
    review_rounds = int(state.get("review_rounds", 0) or 0)
    previous_review = state.get("review_report", {}) or {}

    # Gate before reviewer LLM call:
    # key blocking issues from previous review must be covered by current tasks.
    is_rework_round = review_rounds > 0 and not bool(previous_review.get("passed"))
    if is_rework_round:
        blocking_issues = extract_blocking_issues(previous_review, max_items=8)
        uncovered = find_uncovered_blocking_issues(tasks, blocking_issues)
        if uncovered:
            review_report = {
                "passed": False,
                "issues": [
                    "回流覆盖检查未通过：以下关键阻塞项尚未被任务清单命中。"
                ]
                + uncovered,
                "suggestions": [
                    "请先补齐上述阻塞项对应任务，再进入评审。",
                    "建议在任务标题中显式包含阻塞项关键词，并补充依赖关系与验收标准。",
                ],
            }
            return _apply_review_outcome(state, review_report, passed=False)

    project_id = str(state.get("project_id", "") or state.get("thread_id", "") or "unknown")
    cache_payload = _build_reviewer_cache_payload(
        req=req,
        fea=fea,
        arch=arch,
        tasks=tasks,
        prompts=prompts,
        previous_review=previous_review,
        review_rounds=review_rounds,
    )
    cached_review = load_cached_review(project_id, cache_payload)
    if cached_review is not None:
        return _apply_review_outcome(
            state,
            review_report=cached_review,
            passed=bool(cached_review.get("passed")),
        )

    compact_context = (
        "请对当前方案进行评审，重点检查遗漏、冲突、不可实施风险与范围过大问题。\n"
        f"需求摘要: {req.get('summary', '')}\n"
        f"关键约束: {summarize_key_list(req.get('constraints', []), max_items=10, max_chars=1200)}\n"
        f"可行性: feasible={fea.get('feasible')} complexity={fea.get('complexity')}\n"
        f"主要风险: {summarize_key_list(fea.get('risks', []), max_items=8, max_chars=1200)}\n"
        f"架构风格: {arch.get('architecture_style', '')}\n"
        f"后端: {summarize_key_list(arch.get('backend', []), max_items=8, max_chars=600)}\n"
        f"前端: {summarize_key_list(arch.get('frontend', []), max_items=8, max_chars=600)}\n"
        f"任务总数: {len(tasks)}\n"
        f"任务摘要:\n{summarize_task_breakdown(tasks, max_items=12)}\n"
        f"提示词总数: {len(prompts)}\n"
        f"提示词摘要:\n{summarize_prompt_pack(prompts, max_items=8)}"
    )
    if is_rework_round:
        compact_context += (
            "\n回流阻塞项摘要:\n"
            f"{summarize_review_feedback(previous_review, max_issues=6, max_suggestions=4)}"
        )

    agent = build_reviewer_agent()
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
    review_report = structured.model_dump()
    save_cached_review(project_id, cache_payload, review_report)
    passed = bool(review_report.get("passed"))
    return _apply_review_outcome(state, review_report, passed=passed)
