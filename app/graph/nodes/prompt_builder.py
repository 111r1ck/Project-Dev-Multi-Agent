import re

from app.agents.prompt_builder_agent import build_prompt_builder_agent
from app.graph.nodes.common import (
    extract_structured_response,
    summarize_review_feedback,
    summarize_task_breakdown,
)
from app.graph.state import ProjectState
from app.services.prompt_cache import load_cached_prompts, save_cached_prompts


PROMPT_BUILD_BATCH_SIZE = 8
PROMPT_BUILD_MAX_TOTAL = 14
PROMPT_BUILD_MAX_P2 = 2


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


def _priority_rank(priority: str) -> int:
    normalized = str(priority or "").strip().upper()
    mapping = {
        "最高": 0,
        "高": 0,
        "P0": 0,
        "中": 1,
        "P1": 1,
        "低": 2,
        "P2": 2,
        "P3": 3,
    }
    return mapping.get(normalized, 2)


def _extract_review_focus_indices(tasks: list[dict], review_report: dict) -> set[int]:
    if not isinstance(review_report, dict):
        return set()
    texts = [str(item) for item in (review_report.get("issues", []) or [])]
    texts.extend(str(item) for item in (review_report.get("suggestions", []) or []))
    if not texts:
        return set()

    focus_indices: set[int] = set()
    for idx, task in enumerate(tasks):
        title = str(task.get("title", "")).strip()
        if not title:
            continue
        if any(title in text for text in texts):
            focus_indices.add(idx)
            continue
        normalized_tokens = re.findall(r"[A-Za-z0-9_\-]{2,}|[\u4e00-\u9fff]{2,}", title)
        if not normalized_tokens:
            continue
        if any(sum(1 for token in normalized_tokens if token in text) >= 2 for text in texts):
            focus_indices.add(idx)
    return focus_indices


def _select_prompt_build_indices(
    tasks: list[dict],
    missing_indices: list[int],
    *,
    focus_indices: set[int],
    max_total: int = PROMPT_BUILD_MAX_TOTAL,
    max_p2: int = PROMPT_BUILD_MAX_P2,
) -> list[int]:
    if not missing_indices:
        return []

    missing_set = set(missing_indices)
    selected: list[int] = []

    focus_candidates = sorted(idx for idx in focus_indices if idx in missing_set)
    for idx in focus_candidates:
        selected.append(idx)
        if len(selected) >= max_total:
            return selected[:max_total]

    p2_count = 0
    sorted_candidates = sorted(
        missing_indices,
        key=lambda idx: (_priority_rank(tasks[idx].get("priority", "")), idx),
    )
    for idx in sorted_candidates:
        if idx in selected:
            continue
        rank = _priority_rank(tasks[idx].get("priority", ""))
        if rank >= 2 and p2_count >= max_p2:
            continue
        selected.append(idx)
        if rank >= 2:
            p2_count += 1
        if len(selected) >= max_total:
            break
    return selected


def prompt_builder_node(state: ProjectState) -> ProjectState:
    all_tasks = state["task_breakdown"]
    project_id = str(state.get("project_id", "") or state.get("thread_id", "") or "unknown")
    review_rounds = int(state.get("review_rounds", 0) or 0)
    review_report = state.get("review_report", {}) or {}
    is_rework_round = review_rounds > 0 and not bool(review_report.get("passed"))
    focus_indices = _extract_review_focus_indices(all_tasks, review_report)

    prompt_slots, missing_indices = load_cached_prompts(project_id, review_rounds, all_tasks)
    if is_rework_round and review_rounds > 0:
        previous_slots, _ = load_cached_prompts(project_id, review_rounds - 1, all_tasks)
        for idx in range(len(all_tasks)):
            if idx in focus_indices:
                continue
            if prompt_slots[idx] is None and previous_slots[idx] is not None:
                prompt_slots[idx] = previous_slots[idx]
        missing_indices = [idx for idx in missing_indices if prompt_slots[idx] is None]

    build_indices = _select_prompt_build_indices(
        all_tasks,
        missing_indices,
        focus_indices=focus_indices,
    )

    if build_indices:
        agent = build_prompt_builder_agent()
    else:
        agent = None

    for batch_start in range(0, len(build_indices), PROMPT_BUILD_BATCH_SIZE):
        batch_indices = build_indices[batch_start : batch_start + PROMPT_BUILD_BATCH_SIZE]
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
