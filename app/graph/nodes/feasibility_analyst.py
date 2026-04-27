from app.agents.feasibility_agent import build_feasibility_agent
from app.config import settings
from app.graph.nodes.common import extract_structured_response
from app.graph.state import ProjectState
from app.services.missing_info_resolver import (
    build_assumption_pack,
    classify_missing_info_levels,
)


def feasibility_analyst_node(state: ProjectState) -> ProjectState:
    agent = build_feasibility_agent()
    result = agent.invoke(
        {
            "messages": [
                {"role": "user", "content": f"请评估以下需求：{state['requirement_doc']}"}
            ]
        }
    )
    structured = extract_structured_response(result)
    levels = classify_missing_info_levels(structured.missing_info)
    must_confirm_count = len(levels.get("must_confirm", []))
    complexity = str(getattr(structured, "complexity", "") or "").strip().lower()
    simple_complexity_markers = {"low", "simple", "s", "小", "低"}
    is_simple_case = complexity in simple_complexity_markers
    need_human_raw = (
        (not structured.feasible)
        or must_confirm_count > 0
        or (len(structured.missing_info) >= 6 and not is_simple_case)
    )
    human_rounds = state.get("human_rounds")
    if human_rounds is None:
        human_rounds = str(state.get("raw_requirement", "")).count("[人工补充]")
    max_human_rounds = state.get("max_human_rounds", settings.human_gate_max_rounds)
    need_human = need_human_raw and human_rounds < max_human_rounds
    errors = list(state.get("errors", []))
    if need_human_raw and not need_human:
        errors.append(
            f"已达到人工补充上限({max_human_rounds})，系统将基于受控假设继续推进到架构阶段。"
        )
        assumption_pack = build_assumption_pack(
            missing_info=structured.missing_info,
            requirement_doc=state.get("requirement_doc", {}),
            project_decisions=state.get("project_decisions", {}),
            human_feedback_notes=state.get("human_feedback_notes", []),
        )
    else:
        assumption_pack = state.get("assumption_pack", {})

    return {
        **state,
        "feasibility_report": structured.model_dump(),
        "assumption_pack": assumption_pack,
        "need_human": need_human,
        "errors": errors,
        "next_step": "human_gate" if need_human else "architect",
    }
