from app.agents.prompt_builder_agent import build_prompt_builder_agent
from app.graph.nodes.common import (
    extract_structured_response,
    summarize_review_feedback,
    summarize_task_breakdown,
)
from app.graph.state import ProjectState
from app.services.prompt_cache import load_cached_prompts, save_cached_prompts


PROMPT_BUILD_BATCH_SIZE = 8


def _build_fallback_prompt(task: dict) -> dict:
    title = task.get("title", "未命名任务")
    description = task.get("description", "")
    priority = task.get("priority", "")
    owner = task.get("owner_role", "")
    depends_on = task.get("depends_on", [])
    deps_text = ", ".join(depends_on) if depends_on else "无"
    return {
        "task_title": title,
        "coding_prompt": (
            f"请实现任务：{title}\n"
            f"任务描述：{description}\n"
            f"优先级：{priority}，责任角色：{owner}，依赖：{deps_text}\n"
            "要求：给出可运行实现，包含接口/数据结构/异常处理；"
            "如果存在外部依赖，提供可替代mock方案。"
        ),
        "test_prompt": (
            f"请为任务《{title}》设计测试。\n"
            "覆盖：正常流程、异常流程、边界条件、回归点。\n"
            "输出：测试用例清单、关键断言、验收标准。"
        ),
        "is_fallback": True,
    }


def _align_prompt_pack_to_tasks(
    task_breakdown: list[dict],
    prompt_pack: list[dict],
) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for item in prompt_pack:
        key = str(item.get("task_title", "")).strip()
        if not key:
            continue
        buckets.setdefault(key, []).append(item)

    aligned: list[dict] = []
    for task in task_breakdown:
        title = str(task.get("title", "")).strip()
        candidates = buckets.get(title, [])
        if candidates:
            chosen = candidates.pop(0)
            coding_prompt = str(chosen.get("coding_prompt", "")).strip()
            test_prompt = str(chosen.get("test_prompt", "")).strip()
            if coding_prompt and test_prompt:
                aligned.append(
                    {
                        "task_title": title,
                        "coding_prompt": coding_prompt,
                        "test_prompt": test_prompt,
                        "is_fallback": bool(chosen.get("is_fallback", False)),
                    }
                )
                continue
        aligned.append(_build_fallback_prompt(task))
    return aligned


def prompt_builder_node(state: ProjectState) -> ProjectState:
    all_tasks = state["task_breakdown"]
    project_id = str(state.get("project_id", "") or state.get("thread_id", "") or "unknown")
    review_rounds = int(state.get("review_rounds", 0) or 0)

    prompt_slots, missing_indices = load_cached_prompts(project_id, review_rounds, all_tasks)
    if missing_indices:
        agent = build_prompt_builder_agent()
    else:
        agent = None

    for batch_start in range(0, len(missing_indices), PROMPT_BUILD_BATCH_SIZE):
        batch_indices = missing_indices[batch_start : batch_start + PROMPT_BUILD_BATCH_SIZE]
        missing_tasks = [all_tasks[i] for i in batch_indices]
        task_summary = summarize_task_breakdown(
            missing_tasks,
            max_items=PROMPT_BUILD_BATCH_SIZE,
        )
        compact_context = (
            "请为以下任务生成编码提示词与测试提示词。"
            "只针对列出的任务生成，避免重复扩写。\n"
            f"{task_summary}"
        )

        review_report = state.get("review_report", {}) or {}
        is_rework_round = review_rounds > 0 and not bool(review_report.get("passed"))
        if is_rework_round:
            review_feedback = summarize_review_feedback(
                review_report, max_issues=5, max_suggestions=5
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

        assert agent is not None
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
        generated_prompt_pack = [item.model_dump() for item in structured.prompts]
        aligned_generated = _align_prompt_pack_to_tasks(missing_tasks, generated_prompt_pack)

        task_prompt_pairs: list[tuple[dict, dict]] = []
        for idx, prompt in zip(batch_indices, aligned_generated):
            prompt_slots[idx] = prompt
            task_prompt_pairs.append((all_tasks[idx], prompt))
        save_cached_prompts(project_id, review_rounds, task_prompt_pairs)

    prompt_pack: list[dict] = []
    for idx, task in enumerate(all_tasks):
        cached = prompt_slots[idx]
        if cached is not None:
            prompt_pack.append(cached)
        else:
            prompt_pack.append(_build_fallback_prompt(task))

    return {
        **state,
        "prompt_pack": prompt_pack,
        "next_step": "reviewer",
    }
