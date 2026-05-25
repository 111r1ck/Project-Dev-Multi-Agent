from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any


_LOGGER = logging.getLogger("app.observability")
_LOCK = threading.RLock()
_COUNTERS: dict[str, float] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _labels_suffix(labels: dict[str, Any]) -> str:
    if not labels:
        return ""
    parts = [f"{k}={labels[k]}" for k in sorted(labels)]
    return "|" + ",".join(parts)


def start_timer() -> float:
    return time.perf_counter()


def increment(metric: str, value: float = 1.0, **labels: Any) -> None:
    key = f"{metric}{_labels_suffix(labels)}"
    with _LOCK:
        _COUNTERS[key] = _COUNTERS.get(key, 0.0) + float(value)


def observe_duration(metric_prefix: str, duration_ms: float, **labels: Any) -> None:
    increment(f"{metric_prefix}_count", 1.0, **labels)
    increment(f"{metric_prefix}_sum_ms", float(duration_ms), **labels)


def log_event(event: str, **fields: Any) -> None:
    payload = {
        "ts": _now_iso(),
        "event": event,
        **fields,
    }
    _LOGGER.info(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def track_operation(
    *,
    domain: str,
    operation: str,
    status: str,
    started_at: float,
    **fields: Any,
) -> float:
    duration_ms = round((time.perf_counter() - started_at) * 1000.0, 3)
    increment("op_total", 1.0, domain=domain, operation=operation, status=status)
    observe_duration("op_duration", duration_ms, domain=domain, operation=operation)
    log_event(
        "operation",
        domain=domain,
        operation=operation,
        status=status,
        duration_ms=duration_ms,
        **fields,
    )
    return duration_ms


def snapshot_metrics() -> dict[str, float]:
    with _LOCK:
        return dict(_COUNTERS)


def reset_metrics() -> None:
    with _LOCK:
        _COUNTERS.clear()
