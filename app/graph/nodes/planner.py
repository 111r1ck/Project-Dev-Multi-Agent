from app.agents.planner_agent import build_planner_agent
from app.graph.nodes.common import (
    compact_json,
    extract_structured_response,
    summarize_review_feedback,
)
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

    review_rounds = int(state.get("review_rounds", 0) or 0)
    review_report = state.get("review_report", {}) or {}
    is_rework_round = review_rounds > 0 and not bool(review_report.get("passed"))
    if is_rework_round:
        review_feedback = summarize_review_feedback(
            review_report, max_issues=10, max_suggestions=10
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

    return {
        **state,
        "task_breakdown": [task.model_dump() for task in structured.tasks],
        "next_step": "prompt_builder",
    }
