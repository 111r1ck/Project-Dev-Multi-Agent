from langgraph.types import interrupt

from app.graph.state import ProjectState


def human_gate_node(state: ProjectState) -> ProjectState:
    human_feedback = interrupt(
        {
            "type": "missing_requirement_info",
            "message": "需求信息缺失较多，请人工补充后继续。",
            "missing_info": state.get("feasibility_report", {}).get("missing_info", []),
        }
    )

    notes = list(state.get("human_feedback_notes", []))
    notes.append(human_feedback)
    notes = notes[-10:]

    return {
        **state,
        "human_feedback_notes": notes,
        "human_rounds": state.get("human_rounds", 0) + 1,
        "need_human": False,
        "next_step": "requirement_analyst",
    }
