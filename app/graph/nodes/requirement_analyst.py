from app.agents.requirement_agent import build_requirement_agent
from app.graph.nodes.common import extract_structured_response
from app.graph.state import ProjectState


def requirement_analyst_node(state: ProjectState) -> ProjectState:
    agent = build_requirement_agent()
    result = agent.invoke(
        {"messages": [{"role": "user", "content": state["raw_requirement"]}]}
    )
    structured = extract_structured_response(result)

    return {
        **state,
        "requirement_doc": structured.model_dump(),
        "next_step": "feasibility_analyst",
    }
