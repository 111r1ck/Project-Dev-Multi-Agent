from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api.middleware_rate_limit import RedisRateLimitMiddleware
from app.api.routes_agents import router as agents_router
from app.api.routes_projects import router as projects_router
from app.api.routes_runs import router as runs_router
from app.config import settings

app = FastAPI(title=settings.app_name)
if settings.rate_limit_enabled:
    app.add_middleware(RedisRateLimitMiddleware)
app.include_router(agents_router)
app.include_router(projects_router)
app.include_router(runs_router)

WEB_INDEX_PATH = Path(__file__).resolve().parent / "web" / "index.html"


@app.get("/")
async def index():
    return FileResponse(WEB_INDEX_PATH)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
