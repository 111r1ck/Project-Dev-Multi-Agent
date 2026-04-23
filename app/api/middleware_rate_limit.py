from __future__ import annotations

from dataclasses import dataclass

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings

try:
    import redis.asyncio as redis
except ImportError:  # pragma: no cover
    redis = None


@dataclass(frozen=True)
class RateRule:
    path_prefix: str
    limit: int


class RedisRateLimitMiddleware(BaseHTTPMiddleware):
    LUA_INCR_EXPIRE = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""

    def __init__(self, app):
        super().__init__(app)
        self.window_seconds = settings.rate_limit_window_seconds
        self.prefix = settings.rate_limit_prefix
        self.rules = [
            RateRule("/runs", settings.rate_limit_runs_per_window),
        ]
        self.redis_client = (
            redis.from_url(settings.redis_url, decode_responses=True)
            if redis is not None
            else None
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return await call_next(request)

        rule = self._match_rule(request.url.path)
        if rule is None or rule.limit <= 0:
            return await call_next(request)

        if self.redis_client is None:
            return await call_next(request)

        allowed, remaining = await self._allow(request, rule)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "path": request.url.path,
                    "limit": rule.limit,
                    "window_seconds": self.window_seconds,
                },
                headers={"X-RateLimit-Remaining": str(max(remaining, 0))},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(max(remaining, 0))
        return response

    def _match_rule(self, path: str) -> RateRule | None:
        for rule in self.rules:
            if path == rule.path_prefix or path.startswith(f"{rule.path_prefix}/"):
                return rule
        return None

    async def _allow(self, request: Request, rule: RateRule) -> tuple[bool, int]:
        client_ip = self._client_ip(request)
        key = f"{self.prefix}:{request.method}:{rule.path_prefix}:{client_ip}"
        current = await self.redis_client.eval(
            self.LUA_INCR_EXPIRE,
            1,
            key,
            self.window_seconds,
        )
        current_count = int(current)
        remaining = rule.limit - current_count
        return current_count <= rule.limit, remaining

    @staticmethod
    def _client_ip(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client and request.client.host:
            return request.client.host
        return "unknown"
