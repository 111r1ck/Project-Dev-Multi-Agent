from app.agents.prompt_builder_agent import build_prompt_builder_agent
from app.graph.nodes.common import (
    extract_structured_response,
    summarize_review_feedback,
    summarize_task_breakdown,
)
from app.graph.state import ProjectState


def prompt_builder_node(state: ProjectState) -> ProjectState:
    task_summary = summarize_task_breakdown(state["task_breakdown"], max_items=12)
    compact_context = (
        "请为以下任务生成编码提示词与测试提示词。"
        "只针对列出的任务生成，避免重复扩写。\n"
        f"{task_summary}"
    )

    review_rounds = int(state.get("review_rounds", 0) or 0)
    review_report = state.get("review_report", {}) or {}
    is_rework_round = review_rounds > 0 and not bool(review_report.get("passed"))
    if is_rework_round:
        review_feedback = summarize_review_feedback(
            review_report, max_issues=10, max_suggestions=10
        )
        compact_context += (
            "\n\n[回流修复模式]\n"
            "上一轮评审未通过。请基于以下评审问题与建议，优先生成能修复这些问题的提示词：\n"
            f"{review_feedback}\n"
            "要求：\n"
            "1) 每条提示词要明确其对应要修复的问题。\n"
            "2) 测试提示词需包含回归测试要点，覆盖关键issues。\n"
            "3) 避免无关扩写。"
        )

    agent = build_prompt_builder_agent()
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": compact_context,
                }
            ]
        }
    )
    structured = extract_structured_response(result)

    return {
        **state,
        "prompt_pack": [item.model_dump() for item in structured.prompts],
        "next_step": "reviewer",
    }
