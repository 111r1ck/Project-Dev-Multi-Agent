from app.agents.reviewer_agent import build_reviewer_agent
from app.config import settings
from app.graph.nodes.common import (
    compact_json,
    extract_structured_response,
    summarize_prompt_pack,
    summarize_task_breakdown,
)
from app.graph.state import ProjectState


def reviewer_node(state: ProjectState) -> ProjectState:
    req = state["requirement_doc"]
    fea = state["feasibility_report"]
    arch = state["architecture_plan"]
    tasks = state.get("task_breakdown", [])
    prompts = state.get("prompt_pack", [])

    compact_context = (
        "请对当前方案进行评审，重点检查遗漏、冲突、不可实施风险与范围过大问题。\n"
        f"需求摘要: {req.get('summary', '')}\n"
        f"关键约束: {compact_json(req.get('constraints', [])[:8], max_chars=1200)}\n"
        f"可行性: feasible={fea.get('feasible')} complexity={fea.get('complexity')}\n"
        f"主要风险: {compact_json(fea.get('risks', [])[:6], max_chars=1200)}\n"
        f"架构风格: {arch.get('architecture_style', '')}\n"
        f"后端: {compact_json(arch.get('backend', []), max_chars=600)}\n"
        f"前端: {compact_json(arch.get('frontend', []), max_chars=600)}\n"
        f"任务总数: {len(tasks)}\n"
        f"任务摘要:\n{summarize_task_breakdown(tasks, max_items=10)}\n"
        f"提示词总数: {len(prompts)}\n"
        f"提示词摘要:\n{summarize_prompt_pack(prompts, max_items=8)}"
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
    passed = bool(review_report.get("passed"))
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
