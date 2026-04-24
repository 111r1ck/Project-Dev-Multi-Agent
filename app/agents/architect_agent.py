from langchain.agents import create_agent

from app.agents.llm import get_llm
from app.agents.schemas import ArchitecturePlan
from app.tools.architecture_tools import suggest_architecture_style


def build_architect_agent():
    return create_agent(
        model=get_llm("architect"),
        tools=[suggest_architecture_style],
        system_prompt=(
            "你是系统架构师，负责生成MVP可落地架构方案。"
            "任务目标："
            "1) 基于需求与可行性报告输出可实施架构；"
            "2) 明确技术栈、模块职责、数据实体；"
            "3) 控制复杂度，避免超前设计。"
            "设计原则："
            "优先模块化单体+清晰边界，必要时再预留拆分点；"
            "每个模块必须有明确职责，不要重复或交叉失控；"
            "架构选择应与已知约束一致（并发、成本、合规、团队能力）；"
            "对未决信息采用保守默认策略，并显式体现在方案中。"
            "输出要求："
            "必须严格遵循schema；"
            "modules 字段需可用于直接任务拆解；"
            "不输出与MVP无关的大规模远期设计。"
        ),
        response_format=ArchitecturePlan,
    )
