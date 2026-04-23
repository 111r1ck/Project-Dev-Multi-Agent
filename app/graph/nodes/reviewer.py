from app.agents.reviewer_agent import build_reviewer_agent
from app.graph.nodes.common import extract_structured_response
from app.graph.state import ProjectState


def reviewer_node(state: ProjectState) -> ProjectState:
    agent = build_reviewer_agent()
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"需求：{state['requirement_doc']}\n"
                        f"可行性：{state['feasibility_report']}\n"
                        f"架构：{state['architecture_plan']}\n"
                        f"任务：{state['task_breakdown']}\n"
                        f"提示词：{state['prompt_pack']}"
                    ),
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
