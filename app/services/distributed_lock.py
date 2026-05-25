from __future__ import annotations

import secrets
import threading
from typing import Any

from app.config import settings

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None


_CLIENT = None
_CLIENT_LOCK = threading.RLock()

_LUA_RELEASE_IF_OWNER = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


def _get_client():
    global _CLIENT
    if not settings.distributed_lock_enabled or redis is None:
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


def _lock_key(project_id: str) -> str:
    return f"{settings.distributed_lock_prefix}:{project_id}"


def acquire_project_execution_lock(project_id: str) -> tuple[bool, str | None]:
    """
    Acquire a cross-process execution lock for one project.

    Returns:
      - (True, token): lock acquired and token should be used for release
      - (False, None): lock exists and cannot be acquired
      - (True, None): distributed lock disabled/unavailable (fail-open)
    """
    client = _get_client()
    if client is None:
        return True, None

    token = secrets.token_hex(16)
    ttl = max(int(settings.distributed_lock_ttl_seconds), 30)
    try:
        acquired = bool(client.set(_lock_key(project_id), token, nx=True, ex=ttl))
    except Exception:
        # Fail-open to keep service available when redis is transiently unavailable.
        return True, None
    if not acquired:
        return False, None
    return True, token


def release_project_execution_lock(project_id: str, token: str | None) -> None:
    client = _get_client()
    if client is None or not token:
        return
    try:
        client.eval(_LUA_RELEASE_IF_OWNER, 1, _lock_key(project_id), token)
    except Exception:
        return

