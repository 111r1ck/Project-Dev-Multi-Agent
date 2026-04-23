from langchain.agents import create_agent

from app.agents.llm import get_llm
from app.agents.schemas import PlannerOutput
from app.tools.planning_tools import estimate_task_size


def build_planner_agent():
    return create_agent(
        model=get_llm("planner"),
        tools=[estimate_task_size],
        system_prompt=(
            "你是研发项目经理。"
            "根据架构方案拆分里程碑和任务，输出优先级、依赖关系和责任角色。"
            "输出必须严格遵循schema。"
        ),
        response_format=PlannerOutput,
    )
