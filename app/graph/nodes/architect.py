from app.agents.architect_agent import build_architect_agent
from app.graph.nodes.common import compact_json, extract_structured_response
from app.graph.state import ProjectState


def architect_node(state: ProjectState) -> ProjectState:
    req = state["requirement_doc"]
    fea = state["feasibility_report"]
    compact_context = (
        "请基于以下摘要生成架构方案。\n"
        f"需求摘要: {req.get('summary', '')}\n"
        f"角色: {compact_json(req.get('roles', []), max_chars=800)}\n"
        f"模块: {compact_json(req.get('modules', []), max_chars=1000)}\n"
        f"约束: {compact_json(req.get('constraints', []), max_chars=1200)}\n"
        f"可行性: feasible={fea.get('feasible')} complexity={fea.get('complexity')}\n"
        f"主要风险: {compact_json(fea.get('risks', [])[:5], max_chars=1200)}\n"
        f"MVP范围: {compact_json(fea.get('mvp_scope', [])[:8], max_chars=1200)}"
    )

    agent = build_architect_agent()
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
        "architecture_plan": structured.model_dump(),
        "next_step": "planner",
    }
