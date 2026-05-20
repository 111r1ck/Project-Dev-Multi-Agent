from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any

from app.services.runtime_settings import get_runtime_settings

_PERSIST_KEY_MAP = {
    "llm_provider": "LLM_PROVIDER",
    "llm_model": "LLM_MODEL",
    "llm_temperature": "LLM_TEMPERATURE",
    "llm_enable_thinking": "LLM_ENABLE_THINKING",
    "requirement_llm_model": "REQUIREMENT_LLM_MODEL",
    "feasibility_llm_model": "FEASIBILITY_LLM_MODEL",
    "architect_llm_model": "ARCHITECT_LLM_MODEL",
    "planner_llm_model": "PLANNER_LLM_MODEL",
    "prompt_builder_llm_model": "PROMPT_BUILDER_LLM_MODEL",
    "reviewer_llm_model": "REVIEWER_LLM_MODEL",
    "openai_api_key": "OPENAI_API_KEY",
    "openai_base_url": "OPENAI_BASE_URL",
    "azure_openai_api_key": "AZURE_OPENAI_API_KEY",
    "azure_openai_endpoint": "AZURE_OPENAI_ENDPOINT",
    "azure_openai_deployment": "AZURE_OPENAI_DEPLOYMENT",
    "azure_openai_api_version": "AZURE_OPENAI_API_VERSION",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "google_api_key": "GOOGLE_API_KEY",
    "ollama_base_url": "OLLAMA_BASE_URL",
    "openrouter_api_key": "OPENROUTER_API_KEY",
    "openrouter_base_url": "OPENROUTER_BASE_URL",
    "agent_llm_profiles": "AGENT_LLM_PROFILES_JSON",
}


def _stringify_env_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).replace("\n", " ").replace("\r", " ").strip()


def persist_runtime_settings_to_env(env_path: Path | None = None) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    target = env_path or (root / ".env")
    current = get_runtime_settings(reveal_secrets=True)

    if target.exists():
        lines = target.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    key_pattern = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
    index_by_key: dict[str, int] = {}
    for i, line in enumerate(lines):
        match = key_pattern.match(line)
        if match:
            index_by_key[match.group(1)] = i

    updated_keys: list[str] = []
    for runtime_key, env_key in _PERSIST_KEY_MAP.items():
        value = _stringify_env_value(current.get(runtime_key, ""))
        new_line = f"{env_key}={value}"
        if env_key in index_by_key:
            lines[index_by_key[env_key]] = new_line
        else:
            lines.append(new_line)
        updated_keys.append(env_key)

    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "env_path": str(target),
        "updated_keys": updated_keys,
    }
