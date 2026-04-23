from app.agents.architect_agent import build_architect_agent
from app.graph.nodes.common import extract_structured_response
from app.graph.state import ProjectState


def architect_node(state: ProjectState) -> ProjectState:
    agent = build_architect_agent()
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"需求文档：{state['requirement_doc']}\n"
                        f"可行性报告：{state['feasibility_report']}"
                    ),
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
