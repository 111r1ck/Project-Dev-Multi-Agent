from app.graph.state import ProjectState


def next_route(state: ProjectState) -> str:
    return state.get("next_step", "finish")
