from __future__ import annotations

import hashlib
import json
import threading
from typing import Any

from app.config import settings
from app.services.runtime_settings import get_runtime_settings

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None


_CLIENT = None
_CLIENT_LOCK = threading.RLock()


def _normalize_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(task.get("title", "")).strip(),
        "description": str(task.get("description", "")).strip(),
        "priority": str(task.get("priority", "")).strip(),
        "depends_on": [str(i).strip() for i in (task.get("depends_on", []) or [])],
        "owner_role": str(task.get("owner_role", "")).strip(),
    }


def _task_signature(task: dict[str, Any]) -> str:
    payload = _normalize_task(task)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _prompt_builder_model_scope() -> str:
    runtime = get_runtime_settings(reveal_secrets=True)
    provider = str(runtime.get("llm_provider", settings.llm_provider)).strip().lower()
    model = (
        str(runtime.get("prompt_builder_llm_model", "") or "").strip()
        or str(runtime.get("llm_model", "") or "").strip()
        or settings.prompt_builder_llm_model
        or settings.llm_model
    )
    return f"{provider}:{model}"


def _cache_key(project_id: str, review_rounds: int, task: dict[str, Any]) -> str:
    scope = _prompt_builder_model_scope()
    signature = _task_signature(task)
    return (
        f"{settings.prompt_cache_prefix}:{project_id}:"
        f"rr{int(review_rounds)}:{scope}:{signature}"
    )


def _get_client():
    global _CLIENT
    if not settings.prompt_cache_enabled or redis is None:
        return None
    with _CLIENT_LOCK:
        if _CLIENT is None:
            _CLIENT = redis.Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            )
        return _CLIENT


def load_cached_prompts(
    project_id: str,
    review_rounds: int,
    tasks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any] | None], list[int]]:
    client = _get_client()
    placeholders: list[dict[str, Any] | None] = [None] * len(tasks)
    if client is None:
        return placeholders, list(range(len(tasks)))

    missing_indices: list[int] = []
    for idx, task in enumerate(tasks):
        key = _cache_key(project_id, review_rounds, task)
        try:
            value = client.get(key)
        except Exception:
            # Fail-open: skip cache on transient redis errors.
            value = None

        if not value:
            missing_indices.append(idx)
            continue

        try:
            parsed = json.loads(value)
        except Exception:
            missing_indices.append(idx)
            continue

        task_title = str(parsed.get("task_title", "")).strip()
        coding_prompt = str(parsed.get("coding_prompt", "")).strip()
        test_prompt = str(parsed.get("test_prompt", "")).strip()
        if not task_title or not coding_prompt or not test_prompt:
            missing_indices.append(idx)
            continue
        placeholders[idx] = {
            "task_title": task_title,
            "coding_prompt": coding_prompt,
            "test_prompt": test_prompt,
        }

    return placeholders, missing_indices


def save_cached_prompts(
    project_id: str,
    review_rounds: int,
    task_prompt_pairs: list[tuple[dict[str, Any], dict[str, Any]]],
) -> None:
    client = _get_client()
    if client is None or not task_prompt_pairs:
        return

    ttl = max(int(settings.prompt_cache_ttl_seconds), 60)
    for task, prompt in task_prompt_pairs:
        key = _cache_key(project_id, review_rounds, task)
        payload = {
            "task_title": str(prompt.get("task_title", "")).strip(),
            "coding_prompt": str(prompt.get("coding_prompt", "")).strip(),
            "test_prompt": str(prompt.get("test_prompt", "")).strip(),
        }
        if not payload["task_title"] or not payload["coding_prompt"] or not payload["test_prompt"]:
            continue
        try:
            client.setex(
                key,
                ttl,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            )
        except Exception:
            # Fail-open: do not break workflow for cache write errors.
            continue

