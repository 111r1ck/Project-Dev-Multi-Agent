from langgraph.types import interrupt

from app.graph.state import ProjectState
from app.services.requirement_parser import merge_human_feedback


def human_gate_node(state: ProjectState) -> ProjectState:
    human_feedback = interrupt(
        {
            "type": "missing_requirement_info",
            "message": "需求信息缺失较多，请人工补充后继续。",
            "missing_info": state.get("feasibility_report", {}).get("missing_info", []),
        }
    )

    merged_requirement = merge_human_feedback(
        state["raw_requirement"], str(human_feedback)
    )

    return {
        **state,
        "raw_requirement": merged_requirement,
        "human_rounds": state.get("human_rounds", 0) + 1,
        "need_human": False,
        "next_step": "requirement_analyst",
    }
