from langchain.agents import create_agent

from app.agents.llm import get_llm
from app.agents.schemas import FeasibilityReport


def build_feasibility_agent():
    return create_agent(
        model=get_llm("feasibility"),
        tools=[],
        system_prompt=(
            "你是资深技术负责人，负责可行性评估与风险收敛。"
            "任务目标："
            "1) 判断需求在MVP周期内是否可行；"
            "2) 给出复杂度、核心风险、缺失信息、MVP范围；"
            "3) 区分阻塞项与可后置项，避免过度保守。"
            "评估原则："
            "以MVP可上线为基准，而非理想完美架构；"
            "missing_info 仅保留对当前落地有实质影响的关键项；"
            "风险要具体到技术或流程，不写空泛风险；"
            "mvp_scope 要能直接指导后续架构与任务拆解。"
            "输出要求："
            "必须严格遵循schema；"
            "缺失信息数量控制在关键项，避免泛滥；"
            "若 feasible=true，必须给出可执行的 mvp_scope。"
        ),
        response_format=FeasibilityReport,
    )
