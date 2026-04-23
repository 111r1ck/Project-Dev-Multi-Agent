from app.agents.planner_agent import build_planner_agent
from app.graph.nodes.common import extract_structured_response
from app.graph.state import ProjectState


def planner_node(state: ProjectState) -> ProjectState:
    agent = build_planner_agent()
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"需求：{state['requirement_doc']}\n"
                        f"架构：{state['architecture_plan']}"
                    ),
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
