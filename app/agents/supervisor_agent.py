from langchain.agents import create_agent

from app.agents.llm import get_llm


def build_supervisor_agent():
    return create_agent(
        model=get_llm(),
        tools=[],
        system_prompt=(
            "你是多Agent项目总控。"
            "根据当前状态决定下一步执行哪个专家节点。"
            "只关注流程推进，不重复产出专家内容。"
        ),
    )
