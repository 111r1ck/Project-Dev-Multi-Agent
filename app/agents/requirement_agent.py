from langchain.agents import create_agent

from app.agents.llm import get_llm
from app.agents.schemas import RequirementDoc
from app.tools.requirement_tools import (
    detect_requirement_gaps,
    extract_plain_text_requirement,
)


def build_requirement_agent():
    return create_agent(
        model=get_llm("requirement"),
        tools=[extract_plain_text_requirement, detect_requirement_gaps],
        system_prompt=(
            "你是资深需求分析师。"
            "目标：把原始项目需求整理成结构化需求文档。"
            "输出必须严格遵循给定schema。"
        ),
        response_format=RequirementDoc,
    )
