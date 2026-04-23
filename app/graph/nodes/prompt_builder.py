from app.agents.prompt_builder_agent import build_prompt_builder_agent
from app.graph.nodes.common import extract_structured_response, summarize_task_breakdown
from app.graph.state import ProjectState


def prompt_builder_node(state: ProjectState) -> ProjectState:
    task_summary = summarize_task_breakdown(state["task_breakdown"], max_items=12)
    compact_context = (
        "请为以下任务生成编码提示词与测试提示词。"
        "只针对列出的任务生成，避免重复扩写。\n"
        f"{task_summary}"
    )

    agent = build_prompt_builder_agent()
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": compact_context,
                }
            ]
        }
    )
    structured = extract_structured_response(result)

    return {
        **state,
        "prompt_pack": [item.model_dump() for item in structured.prompts],
        "next_step": "reviewer",
    }
