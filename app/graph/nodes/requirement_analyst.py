from app.agents.requirement_agent import build_requirement_agent
from app.graph.nodes.common import compact_json, extract_structured_response
from app.graph.state import ProjectState


def requirement_analyst_node(state: ProjectState) -> ProjectState:
    notes = state.get("human_feedback_notes", [])
    note_lines = []
    for idx, note in enumerate(notes[-3:], start=1):
        note_lines.append(f"{idx}. {compact_json(note, max_chars=900)}")
    notes_block = "\n".join(note_lines) if note_lines else "(none)"

    prompt = (
        "请基于原始需求和人工补充，输出结构化需求文档。\n"
        f"原始需求:\n{state['raw_requirement']}\n\n"
        f"人工补充(最近3条):\n{notes_block}"
    )

    agent = build_requirement_agent()
    result = agent.invoke(
        {"messages": [{"role": "user", "content": prompt}]}
    )
    structured = extract_structured_response(result)

    return {
        **state,
        "requirement_doc": structured.model_dump(),
        "next_step": "feasibility_analyst",
    }
