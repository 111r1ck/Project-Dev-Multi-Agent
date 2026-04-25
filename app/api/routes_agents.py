from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services.runtime_settings import (
    get_agent_definitions,
    get_runtime_settings,
    get_secret_fields,
    update_runtime_settings,
)
from app.services.env_persistence import persist_runtime_settings_to_env

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentSettingsUpdateRequest(BaseModel):
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_temperature: float | None = None
    llm_enable_thinking: bool | None = None

    requirement_llm_model: str | None = None
    feasibility_llm_model: str | None = None
    architect_llm_model: str | None = None
    planner_llm_model: str | None = None
    prompt_builder_llm_model: str | None = None
    reviewer_llm_model: str | None = None

    openai_api_key: str | None = None
    openai_base_url: str | None = None

    azure_openai_api_key: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str | None = None
    azure_openai_api_version: str | None = None

    anthropic_api_key: str | None = None
    google_api_key: str | None = None

    ollama_base_url: str | None = None

    openrouter_api_key: str | None = None
    openrouter_base_url: str | None = None


@router.get("/settings")
async def get_agents_settings(
    reveal_secrets: bool = Query(False, description="Whether to return raw API keys"),
):
    return {
        "settings": get_runtime_settings(reveal_secrets=reveal_secrets),
        "secret_fields": get_secret_fields(),
        "agent_definitions": get_agent_definitions(),
        "model_options": [
            "gpt-5",
            "gpt-5-mini",
            "qwen3.6-plus",
            "claude-3-5-sonnet-latest",
            "gemini-2.0-flash",
        ],
    }


@router.patch("/settings")
async def patch_agents_settings(req: AgentSettingsUpdateRequest):
    updates: dict[str, Any] = req.model_dump(exclude_none=True)
    updated = update_runtime_settings(updates)
    return {
        "status": "updated",
        "settings": updated,
    }


@router.post("/settings/persist-env")
async def persist_agents_settings_to_env(req: AgentSettingsUpdateRequest | None = None):
    if req is not None:
        updates: dict[str, Any] = req.model_dump(exclude_none=True)
        if updates:
            update_runtime_settings(updates)
    persisted = persist_runtime_settings_to_env()
    return {
        "status": "persisted",
        **persisted,
    }
