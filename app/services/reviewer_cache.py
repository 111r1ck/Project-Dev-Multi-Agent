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


def _reviewer_model_scope() -> str:
    runtime = get_runtime_settings(reveal_secrets=True)
    provider = str(runtime.get("llm_provider", settings.llm_provider)).strip().lower()
    model = (
        str(runtime.get("reviewer_llm_model", "") or "").strip()
        or str(runtime.get("llm_model", "") or "").strip()
        or settings.reviewer_llm_model
        or settings.llm_model
    )
    return f"{provider}:{model}"


def _payload_signature(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cache_key(project_id: str, payload: dict[str, Any]) -> str:
    scope = _reviewer_model_scope()
    signature = _payload_signature(payload)
    return f"{settings.reviewer_cache_prefix}:{project_id}:{scope}:{signature}"


def _get_client():
    global _CLIENT
    if not settings.reviewer_cache_enabled or redis is None:
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


def load_cached_review(project_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    client = _get_client()
    if client is None:
        return None

    key = _cache_key(project_id, payload)
    try:
        value = client.get(key)
    except Exception:
        return None
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    if "passed" not in parsed:
        return None
    parsed.setdefault("issues", [])
    parsed.setdefault("suggestions", [])
    return parsed


def save_cached_review(project_id: str, payload: dict[str, Any], review_report: dict[str, Any]) -> None:
    client = _get_client()
    if client is None:
        return
    if not isinstance(review_report, dict) or "passed" not in review_report:
        return

    key = _cache_key(project_id, payload)
    ttl = max(int(settings.reviewer_cache_ttl_seconds), 60)
    safe_report = {
        "passed": bool(review_report.get("passed")),
        "issues": [str(i) for i in (review_report.get("issues", []) or [])],
        "suggestions": [str(i) for i in (review_report.get("suggestions", []) or [])],
    }
    try:
        client.setex(
            key,
            ttl,
            json.dumps(safe_report, ensure_ascii=False, separators=(",", ":")),
        )
    except Exception:
        return

