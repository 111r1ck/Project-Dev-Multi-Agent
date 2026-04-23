from app.graph.state import ProjectState


def supervisor_node(state: ProjectState) -> ProjectState:
    if state.get("next_step") in {
        "requirement_analyst",
        "feasibility_analyst",
        "architect",
        "planner",
        "prompt_builder",
        "reviewer",
        "human_gate",
        "finish",
    }:
        return state

    return {
        **state,
        "next_step": "requirement_analyst",
    }
