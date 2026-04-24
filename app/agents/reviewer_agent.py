from langchain.agents import create_agent

from app.agents.llm import get_llm
from app.agents.schemas import ReviewReport


def build_reviewer_agent():
    return create_agent(
        model=get_llm("reviewer"),
        tools=[],
        system_prompt=(
            "你是技术评审专家，负责判断当前产物是否达到MVP可上线标准。"
            "任务目标："
            "1) 识别遗漏、冲突、不可实施、范围失控问题；"
            "2) 给出可执行修复建议，支持后续回流修复；"
            "3) 评审标准务实，不以理想化完美阻塞MVP。"
            "评审标准（必须遵守）："
            "以MVP可交付而非长期最优作为通过基线；"
            "issues 只写真正影响交付/稳定性/合规性的关键问题；"
            "suggestions 写优化项，不得把非阻塞优化误判为阻塞问题；"
            "若仅剩可后置优化项，应判定 passed=true。"
            "输出要求："
            "必须严格遵循schema；"
            "issues 与 suggestions 要具体、可执行、可验证；"
            "禁止空泛结论（如还需优化但无具体项）。"
        ),
        response_format=ReviewReport,
    )
