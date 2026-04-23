from app.agents.planner_agent import build_planner_agent
from app.graph.nodes.common import compact_json, extract_structured_response
from app.graph.state import ProjectState


def planner_node(state: ProjectState) -> ProjectState:
    req = state["requirement_doc"]
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
        f"关键约束: {compact_json(req.get('constraints', [])[:6], max_chars=1000)}\n"
        f"架构风格: {arch.get('architecture_style', '')}\n"
        f"后端技术: {compact_json(arch.get('backend', []), max_chars=600)}\n"
        f"前端技术: {compact_json(arch.get('frontend', []), max_chars=600)}\n"
        f"核心模块: {compact_json(modules, max_chars=1600)}"
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

    return {
        **state,
        "task_breakdown": [task.model_dump() for task in structured.tasks],
        "next_step": "prompt_builder",
    }
