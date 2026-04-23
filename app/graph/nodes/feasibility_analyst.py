from app.agents.feasibility_agent import build_feasibility_agent
from app.config import settings
from app.graph.nodes.common import extract_structured_response
from app.graph.state import ProjectState


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
    need_human_raw = (not structured.feasible) or len(structured.missing_info) >= 3
    human_rounds = state.get("human_rounds")
    if human_rounds is None:
        human_rounds = str(state.get("raw_requirement", "")).count("[人工补充]")
    max_human_rounds = state.get("max_human_rounds", settings.human_gate_max_rounds)
    need_human = need_human_raw and human_rounds < max_human_rounds
    errors = list(state.get("errors", []))
    if need_human_raw and not need_human:
        errors.append(
            f"已达到人工补充上限({max_human_rounds})，按默认策略继续推进到架构阶段。"
        )

    return {
        **state,
        "feasibility_report": structured.model_dump(),
        "need_human": need_human,
        "errors": errors,
        "next_step": "human_gate" if need_human else "architect",
    }
