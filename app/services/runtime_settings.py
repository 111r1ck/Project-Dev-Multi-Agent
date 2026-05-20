from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from typing import Any

from app.config import settings

_LOCK = threading.RLock()

_SECRET_FIELDS = {
    "openai_api_key",
    "azure_openai_api_key",
    "anthropic_api_key",
    "google_api_key",
    "openrouter_api_key",
}


def _load_agent_profiles_from_env() -> dict[str, Any]:
    raw = os.getenv("AGENT_LLM_PROFILES_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


_DEFAULTS: dict[str, Any] = {
    "llm_provider": settings.llm_provider,
    "llm_model": settings.llm_model,
    "llm_temperature": settings.llm_temperature,
    "llm_enable_thinking": settings.llm_enable_thinking,
    "requirement_llm_model": settings.requirement_llm_model,
    "feasibility_llm_model": settings.feasibility_llm_model,
    "architect_llm_model": settings.architect_llm_model,
    "planner_llm_model": settings.planner_llm_model,
    "prompt_builder_llm_model": settings.prompt_builder_llm_model,
    "reviewer_llm_model": settings.reviewer_llm_model,
    "openai_api_key": settings.openai_api_key,
    "openai_base_url": settings.openai_base_url,
    "azure_openai_api_key": settings.azure_openai_api_key,
    "azure_openai_endpoint": settings.azure_openai_endpoint,
    "azure_openai_deployment": settings.azure_openai_deployment,
    "azure_openai_api_version": settings.azure_openai_api_version,
    "anthropic_api_key": settings.anthropic_api_key,
    "google_api_key": settings.google_api_key,
    "ollama_base_url": settings.ollama_base_url,
    "openrouter_api_key": settings.openrouter_api_key,
    "openrouter_base_url": settings.openrouter_base_url,
    "agent_llm_profiles": _load_agent_profiles_from_env(),
}

_STATE: dict[str, Any] = deepcopy(_DEFAULTS)


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def get_runtime_settings(*, reveal_secrets: bool = False) -> dict[str, Any]:
    with _LOCK:
        data = deepcopy(_STATE)

    if reveal_secrets:
        return data

    for key in _SECRET_FIELDS:
        raw = str(data.get(key, "") or "")
        data[key] = _mask_secret(raw)

    profiles = data.get("agent_llm_profiles", {})
    if isinstance(profiles, dict):
        masked_profiles: dict[str, Any] = {}
        for agent_key, profile in profiles.items():
            if not isinstance(profile, dict):
                continue
            prof = deepcopy(profile)
            for secret_key in _SECRET_FIELDS:
                if secret_key in prof:
                    prof[secret_key] = _mask_secret(str(prof.get(secret_key, "") or ""))
            masked_profiles[str(agent_key)] = prof
        data["agent_llm_profiles"] = masked_profiles
    return data


def update_runtime_settings(updates: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        for key, value in updates.items():
            if key not in _STATE:
                continue
            if key == "agent_llm_profiles":
                if isinstance(value, dict):
                    normalized: dict[str, Any] = {}
                    for agent_key, profile in value.items():
                        if not isinstance(profile, dict):
                            continue
                        normalized[str(agent_key)] = {
                            str(k): v for k, v in profile.items() if isinstance(k, str)
                        }
                    _STATE[key] = normalized
                continue
            if value is None:
                continue
            if isinstance(_STATE[key], float):
                _STATE[key] = float(value)
                continue
            if isinstance(_STATE[key], bool):
                _STATE[key] = bool(value)
                continue
            if key == "llm_enable_thinking":
                # support optional bool
                if value in ("", None):
                    _STATE[key] = None
                else:
                    _STATE[key] = bool(value)
                continue
            _STATE[key] = str(value).strip()
        return deepcopy(_STATE)


def get_secret_fields() -> list[str]:
    return sorted(_SECRET_FIELDS)


def get_agent_definitions() -> list[dict[str, str]]:
    return [
        {
            "key": "requirement",
            "name_cn": "需求分析 Agent",
            "description_cn": "把原始需求整理为结构化需求文档。",
            "model_field": "requirement_llm_model",
        },
        {
            "key": "feasibility",
            "name_cn": "可行性分析 Agent",
            "description_cn": "评估可行性、复杂度、风险与MVP范围。",
            "model_field": "feasibility_llm_model",
        },
        {
            "key": "architect",
            "name_cn": "架构设计 Agent",
            "description_cn": "输出MVP可落地的系统架构方案。",
            "model_field": "architect_llm_model",
        },
        {
            "key": "planner",
            "name_cn": "任务规划 Agent",
            "description_cn": "拆解里程碑与任务，标注优先级和依赖。",
            "model_field": "planner_llm_model",
        },
        {
            "key": "prompt_builder",
            "name_cn": "提示词构建 Agent",
            "description_cn": "为开发任务生成编码与测试提示词。",
            "model_field": "prompt_builder_llm_model",
        },
        {
            "key": "reviewer",
            "name_cn": "评审 Agent",
            "description_cn": "评审产物是否有遗漏、冲突或不可实施问题。",
            "model_field": "reviewer_llm_model",
        },
    ]
