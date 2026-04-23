from app.graph.state import ProjectState


def render_result(state: ProjectState) -> dict:
    return {
        "requirement_doc": state.get("requirement_doc", {}),
        "feasibility_report": state.get("feasibility_report", {}),
        "architecture_plan": state.get("architecture_plan", {}),
        "task_breakdown": state.get("task_breakdown", []),
        "prompt_pack": state.get("prompt_pack", []),
        "review_report": state.get("review_report", {}),
    }
