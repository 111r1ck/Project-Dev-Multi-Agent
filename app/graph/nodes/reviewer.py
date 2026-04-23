from app.agents.reviewer_agent import build_reviewer_agent
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

    return {
        **state,
        "review_report": structured.model_dump(),
        "next_step": "finish",
    }
