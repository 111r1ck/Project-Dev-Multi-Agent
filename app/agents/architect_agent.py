from langchain.agents import create_agent

from app.agents.llm import get_llm
from app.agents.schemas import ArchitecturePlan
from app.tools.architecture_tools import suggest_architecture_style


def build_architect_agent():
    return create_agent(
        model=get_llm(),
        tools=[suggest_architecture_style],
        system_prompt=(
            "你是系统架构师。"
            "根据需求与可行性报告给出适合MVP落地的架构方案。"
            "输出必须严格遵循schema。"
        ),
        response_format=ArchitecturePlan,
    )
