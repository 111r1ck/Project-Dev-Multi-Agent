from app.agents.prompt_builder_agent import build_prompt_builder_agent
from app.graph.nodes.common import extract_structured_response
from app.graph.state import ProjectState


def prompt_builder_node(state: ProjectState) -> ProjectState:
    agent = build_prompt_builder_agent()
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": f"请为以下任务生成编码提示词与测试提示词：{state['task_breakdown']}",
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
