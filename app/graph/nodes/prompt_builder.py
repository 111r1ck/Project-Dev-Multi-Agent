import re
import time

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
P0_PROMPT_RETRY_MAX_ATTEMPTS = 2
PROMPT_BUILD_MAX_MODEL_CALLS = 6
PROMPT_BUILD_MAX_SECONDS = 45


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


def _build_forced_p0_prompt(task: dict) -> dict:
    title = task.get("title", "未命名任务")
    description = task.get("description", "")
    owner = task.get("owner_role", "")
    depends_on = task.get("depends_on", [])
    deps_text = ", ".join(depends_on) if depends_on else "无"
    return {
        "task_title": title,
        "coding_prompt": (
            f"任务目标：实现《{title}》并满足可上线要求。\n"
            f"任务描述：{description}\n"
            f"责任角色：{owner}；上游依赖：{deps_text}\n"
            "输入：明确接口输入参数、鉴权上下文、边界输入与异常输入。\n"
            "输出：明确成功响应、失败响应、错误码、状态变更与日志字段。\n"
            "约束：幂等性、权限校验、超时与重试策略、回滚或补偿策略。\n"
            "边界：空输入、重复请求、并发冲突、外部依赖异常、部分失败。\n"
            "实现要求：给出关键数据结构、核心流程伪代码、异常处理分支与验收标准。"
        ),
        "test_prompt": (
            f"为《{title}》设计测试并输出可执行清单。\n"
            "必须覆盖：\n"
            "1) 正常流程（主成功路径）；\n"
            "2) 异常流程（参数错误、权限不足、外部依赖失败）；\n"
            "3) 边界条件（空值、重复提交、并发冲突）；\n"
            "4) 回归测试（与上游依赖和历史缺陷相关场景）；\n"
            "5) 验收标准（通过条件与关键断言）。"
        ),
        "is_fallback": False,
        "forced_for_p0": True,
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


def _is_p0_task(task: dict) -> bool:
    return _priority_rank(task.get("priority", "")) == 0


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
    started_at = time.monotonic()
    model_calls = 0
    truncated = False
    truncated_reasons: list[str] = []

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

    def _budget_exhausted() -> bool:
        nonlocal truncated
        if model_calls >= PROMPT_BUILD_MAX_MODEL_CALLS:
            truncated = True
            if "max_model_calls" not in truncated_reasons:
                truncated_reasons.append("max_model_calls")
            return True
        elapsed = time.monotonic() - started_at
        if elapsed >= PROMPT_BUILD_MAX_SECONDS:
            truncated = True
            if "max_seconds" not in truncated_reasons:
                truncated_reasons.append("max_seconds")
            return True
        return False

    def _generate_indices(indices: list[int], *, p0_retry_mode: bool = False) -> None:
        nonlocal agent, model_calls
        if not indices:
            return
        if _budget_exhausted():
            return
        if agent is None:
            agent = build_prompt_builder_agent()
        assert agent is not None

        for batch_start in range(0, len(indices), PROMPT_BUILD_BATCH_SIZE):
            if _budget_exhausted():
                break
            batch_indices = indices[batch_start : batch_start + PROMPT_BUILD_BATCH_SIZE]
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
            if p0_retry_mode:
                compact_context += (
                    "\n\n[P0兜底重试模式]\n"
                    "以下均为P0任务。请严格按任务标题一一输出对应prompt，"
                    "不得缺项、不得改名、不得返回与标题不一致的task_title。"
                )

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
            model_calls += 1
            structured = extract_structured_response(result)
            generated_prompt_pack = [item.model_dump() for item in structured.prompts]
            aligned_generated = _align_prompt_pack_to_tasks(missing_tasks, generated_prompt_pack)

            task_prompt_pairs: list[tuple[dict, dict]] = []
            for idx, prompt in zip(batch_indices, aligned_generated):
                prompt_slots[idx] = prompt
                task_prompt_pairs.append((all_tasks[idx], prompt))
            save_cached_prompts(project_id, review_rounds, task_prompt_pairs)

    _generate_indices(build_indices)

    p0_retry_indices = [
        idx
        for idx, task in enumerate(all_tasks)
        if _is_p0_task(task)
        and (
            prompt_slots[idx] is None
            or bool((prompt_slots[idx] or {}).get("is_fallback", False))
        )
    ]
    retry_attempt = 0
    while p0_retry_indices and retry_attempt < P0_PROMPT_RETRY_MAX_ATTEMPTS and not _budget_exhausted():
        _generate_indices(p0_retry_indices, p0_retry_mode=True)
        p0_retry_indices = [
            idx
            for idx, task in enumerate(all_tasks)
            if _is_p0_task(task)
            and (
                prompt_slots[idx] is None
                or bool((prompt_slots[idx] or {}).get("is_fallback", False))
            )
        ]
        retry_attempt += 1

    if p0_retry_indices:
        forced_pairs: list[tuple[dict, dict]] = []
        for idx in p0_retry_indices:
            forced_prompt = _build_forced_p0_prompt(all_tasks[idx])
            prompt_slots[idx] = forced_prompt
            forced_pairs.append((all_tasks[idx], forced_prompt))
        save_cached_prompts(project_id, review_rounds, forced_pairs)

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
        "prompt_builder_diagnostics": {
            "model_calls": model_calls,
            "max_model_calls": PROMPT_BUILD_MAX_MODEL_CALLS,
            "elapsed_seconds": round(time.monotonic() - started_at, 3),
            "max_seconds": PROMPT_BUILD_MAX_SECONDS,
            "truncated": truncated,
            "truncated_reasons": truncated_reasons,
            "total_tasks": len(all_tasks),
            "generated_tasks": sum(1 for item in prompt_pack if not bool(item.get("is_fallback", False))),
            "fallback_tasks": sum(1 for item in prompt_pack if bool(item.get("is_fallback", False))),
        },
        "next_step": "reviewer",
    }
