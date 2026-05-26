from __future__ import annotations

import json
import queue
import threading
import urllib.request
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.services.observability import increment, log_event

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None


_LOCAL_SEEN: dict[str, float] = {}
_LOCAL_LOCK = threading.RLock()
_REDIS_CLIENT = None
_REDIS_LOCK = threading.RLock()

_QUEUE: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=2000)
_WORKER: threading.Thread | None = None
_WORKER_LOCK = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redis_client():
    global _REDIS_CLIENT
    if redis is None:
        return None
    with _REDIS_LOCK:
        if _REDIS_CLIENT is None:
            _REDIS_CLIENT = redis.Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            )
        return _REDIS_CLIENT


def _idem_key(project_id: str, checkpoint_id: str | None, source: str) -> str:
    cp = (checkpoint_id or "none").strip() or "none"
    return f"{settings.human_interrupt_hook_idempotency_prefix}:{project_id}:{cp}:{source}"


def _mark_once_local(key: str) -> bool:
    ttl = max(int(settings.human_interrupt_hook_idempotency_ttl_seconds), 60)
    with _LOCAL_LOCK:
        # Best-effort cleanup to avoid unbounded growth.
        if len(_LOCAL_SEEN) > 5000:
            _LOCAL_SEEN.clear()
        if key in _LOCAL_SEEN:
            return False
        _LOCAL_SEEN[key] = datetime.now(timezone.utc).timestamp() + ttl
        return True


def _mark_once_distributed(key: str) -> bool:
    client = _redis_client()
    if client is None:
        return _mark_once_local(key)
    ttl = max(int(settings.human_interrupt_hook_idempotency_ttl_seconds), 60)
    try:
        ok = bool(client.set(key, "1", nx=True, ex=ttl))
    except Exception:
        # Degrade to local idempotency on redis failure.
        return _mark_once_local(key)
    return ok


def _send_payload(payload: dict[str, Any]) -> None:
    url = settings.human_interrupt_hook_url.strip()
    if not url:
        return
    headers = {
        "Content-Type": "application/json",
    }
    token = settings.human_interrupt_hook_token.strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url=url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    timeout = max(float(settings.human_interrupt_hook_timeout_seconds), 0.2)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        status_code = int(getattr(resp, "status", 200) or 200)
        if status_code >= 400:
            raise RuntimeError(f"hook http status {status_code}")


def _worker_loop() -> None:
    while True:
        payload = _QUEUE.get()
        try:
            _send_payload(payload)
            increment("human_interrupt_hook_total", 1.0, status="sent")
            log_event(
                "human_interrupt_hook",
                status="sent",
                project_id=payload.get("project_id"),
                checkpoint_id=payload.get("checkpoint_id"),
                source=payload.get("source"),
            )
        except Exception as exc:
            increment("human_interrupt_hook_total", 1.0, status="failed")
            log_event(
                "human_interrupt_hook",
                status="failed",
                project_id=payload.get("project_id"),
                checkpoint_id=payload.get("checkpoint_id"),
                source=payload.get("source"),
                error=str(exc),
            )
        finally:
            _QUEUE.task_done()


def _ensure_worker() -> None:
    global _WORKER
    with _WORKER_LOCK:
        if _WORKER is not None and _WORKER.is_alive():
            return
        _WORKER = threading.Thread(
            target=_worker_loop,
            name="human-interrupt-hook-worker",
            daemon=True,
        )
        _WORKER.start()


def notify_human_interrupt_required(
    *,
    project_id: str,
    checkpoint_id: str | None,
    source: str,
    pending_interrupts: list[Any],
    next_nodes: list[str] | None = None,
) -> bool:
    """
    Non-blocking + idempotent hook trigger.

    Returns True when newly enqueued, False when skipped (disabled/duplicate/queue full).
    """
    if not settings.human_interrupt_hook_enabled:
        return False
    if not settings.human_interrupt_hook_url.strip():
        return False

    idem_key = _idem_key(project_id=project_id, checkpoint_id=checkpoint_id, source=source)
    if not _mark_once_distributed(idem_key):
        increment("human_interrupt_hook_total", 1.0, status="deduped")
        return False

    payload = {
        "schema_version": "1.0",
        "event": "human_input_required",
        "project_id": project_id,
        "checkpoint_id": checkpoint_id,
        "source": source,
        "pending_interrupts": pending_interrupts or [],
        "next_nodes": next_nodes or [],
        "resume_endpoint": f"/runs/{project_id}/resume",
        "occurred_at": _now_iso(),
    }
    _ensure_worker()
    try:
        _QUEUE.put_nowait(payload)
    except queue.Full:
        increment("human_interrupt_hook_total", 1.0, status="queue_full")
        return False
    increment("human_interrupt_hook_total", 1.0, status="queued")
    return True

