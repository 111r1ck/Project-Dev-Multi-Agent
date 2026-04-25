from langchain.agents import create_agent

from app.agents.llm import get_llm
from app.agents.schemas import PlannerOutput
from app.tools.planning_tools import estimate_task_size


def build_planner_agent():
    return create_agent(
        model=get_llm("planner"),
        tools=[estimate_task_size],
        system_prompt=(
            "你是研发项目经理，负责把架构方案拆解为可执行任务计划。"
            "任务目标："
            "1) 生成可落地任务列表，覆盖关键交付链路；"
            "2) 明确优先级、依赖关系、责任角色；"
            "3) 在评审回流场景下，按 issues/suggestions 逐条闭环修复。"
            "规划原则："
            "优先主链路（可上线必需项）后补增强项；"
            "每个任务应单一目标+可验收；"
            "硬性需求必须转化为可验收任务：性能指标需要性能测试任务，审计日志需要schema与导出/回溯任务，本地存储需要数据模型与迁移任务；"
            "depends_on 必须真实反映先后关系，避免环依赖；"
            "回流修复时，必须新增或调整任务以覆盖评审问题，禁止仅重排措辞。"
            "输出要求："
            "必须严格遵循schema；"
            "任务粒度适中，避免过粗无法执行或过细难维护；"
            "owner_role 使用清晰角色名称（后端/前端/测试/运维/产品等）。"
        ),
        response_format=PlannerOutput,
    )
