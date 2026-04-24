from langchain.agents import create_agent

from app.agents.llm import get_llm
from app.agents.schemas import PromptPackOutput


def build_prompt_builder_agent():
    return create_agent(
        model=get_llm("prompt_builder"),
        tools=[],
        system_prompt=(
            "你是AI编程协作专家，负责为每个任务生成高质量编码/测试提示词。"
            "任务目标："
            "1) 为每个任务输出可直接执行的 coding_prompt 与 test_prompt；"
            "2) 提示词要具体、可验证、与任务一一对应；"
            "3) 在评审回流场景下，优先生成能修复 issues 的提示词。"
            "生成原则："
            "coding_prompt 需包含目标、输入输出、关键约束、边界条件；"
            "test_prompt 需包含正常流、异常流、回归点、验收标准；"
            "不写空泛请实现XXX，要给可操作细节；"
            "回流修复时需标明针对哪个问题修复，确保闭环。"
            "输出要求："
            "必须严格遵循schema；"
            "每个 PromptTask 的 task_title 必须对应现有任务；"
            "不输出与任务无关的扩写内容。"
        ),
        response_format=PromptPackOutput,
    )
