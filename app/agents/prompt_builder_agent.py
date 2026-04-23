from langchain.agents import create_agent

from app.agents.llm import get_llm
from app.agents.schemas import PromptPackOutput


def build_prompt_builder_agent():
    return create_agent(
        model=get_llm("prompt_builder"),
        tools=[],
        system_prompt=(
            "你是AI编程协作专家。"
            "请为每个研发任务生成可直接给 Codex / Cursor / Copilot 的编码提示词和测试提示词。"
            "输出必须严格遵循schema。"
        ),
        response_format=PromptPackOutput,
    )
