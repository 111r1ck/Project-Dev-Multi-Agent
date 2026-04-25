from langgraph.types import interrupt

from app.graph.state import ProjectState
from app.services.decision_parser import merge_project_decisions


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
    next_round = state.get("human_rounds", 0) + 1
    project_decisions = merge_project_decisions(
        state.get("project_decisions", {}),
        human_feedback,
        source_round=next_round,
    )

    return {
        **state,
        "human_feedback_notes": notes,
        "project_decisions": project_decisions,
        "human_rounds": next_round,
        "need_human": False,
        "next_step": "requirement_analyst",
    }
