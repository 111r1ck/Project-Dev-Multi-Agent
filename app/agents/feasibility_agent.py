from langchain.agents import create_agent

from app.agents.llm import get_llm
from app.agents.schemas import FeasibilityReport


def build_feasibility_agent():
    return create_agent(
        model=get_llm(),
        tools=[],
        system_prompt=(
            "你是资深技术负责人。"
            "请根据结构化需求评估可行性、复杂度、主要风险、缺失信息和MVP范围。"
            "输出必须严格遵循schema。"
        ),
        response_format=FeasibilityReport,
    )
