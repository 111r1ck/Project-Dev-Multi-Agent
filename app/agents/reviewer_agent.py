from langchain.agents import create_agent

from app.agents.llm import get_llm
from app.agents.schemas import ReviewReport


def build_reviewer_agent():
    return create_agent(
        model=get_llm("reviewer"),
        tools=[],
        system_prompt=(
            "你是技术评审专家。"
            "检查整套输出是否存在遗漏、冲突、范围过大、不可实施问题。"
            "输出必须严格遵循schema。"
        ),
        response_format=ReviewReport,
    )
