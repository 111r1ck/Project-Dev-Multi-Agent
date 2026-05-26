import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


load_dotenv()

_TRUE_SET = {"1", "true", "yes", "on"}
_FALSE_SET = {"0", "false", "no", "off"}


def parse_optional_bool(value: str | None) -> Optional[bool]:
    if value is None:
        return None
    cleaned = value.strip().lower()
    if cleaned == "":
        return None
    if cleaned in _TRUE_SET:
        return True
    if cleaned in _FALSE_SET:
        return False
    return None


def parse_bool(value: str | None, default: bool) -> bool:
    parsed = parse_optional_bool(value)
    return default if parsed is None else parsed


@dataclass(frozen=True)
class Settings:
    app_name: str = "Project Dev Multi-Agent"
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai")
    llm_model: str = os.getenv("LLM_MODEL", os.getenv("OPENAI_MODEL", "gpt-5"))
    llm_temperature: float = float(
        os.getenv("LLM_TEMPERATURE", os.getenv("OPENAI_TEMPERATURE", "0.2"))
    )
    llm_enable_thinking: Optional[bool] = parse_optional_bool(
        os.getenv("LLM_ENABLE_THINKING", "")
    )
    requirement_llm_model: str = os.getenv("REQUIREMENT_LLM_MODEL", "")
    feasibility_llm_model: str = os.getenv("FEASIBILITY_LLM_MODEL", "")
    architect_llm_model: str = os.getenv("ARCHITECT_LLM_MODEL", "")
    planner_llm_model: str = os.getenv("PLANNER_LLM_MODEL", "")
    prompt_builder_llm_model: str = os.getenv("PROMPT_BUILDER_LLM_MODEL", "")
    reviewer_llm_model: str = os.getenv("REVIEWER_LLM_MODEL", "")

    # OpenAI-compatible (OpenAI/Azure/OpenRouter)
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5")
    openai_temperature: float = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "")

    # Azure OpenAI
    azure_openai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_openai_deployment: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
    azure_openai_api_version: str = os.getenv(
        "AZURE_OPENAI_API_VERSION", "2024-10-21"
    )

    # Anthropic
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Google GenAI
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")

    # Ollama
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

    # OpenRouter
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_base_url: str = os.getenv(
        "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
    )

    checkpointer_backend: str = os.getenv("CHECKPOINTER_BACKEND", "memory")
    checkpointer_sqlite_path: str = os.getenv(
        "CHECKPOINTER_SQLITE_PATH", ".data/checkpoints.sqlite"
    )
    checkpointer_postgres_dsn: str = os.getenv("CHECKPOINTER_POSTGRES_DSN", "")
    checkpointer_postgres_pipeline: bool = parse_bool(
        os.getenv("CHECKPOINTER_POSTGRES_PIPELINE", ""), False
    )
    checkpointer_postgres_auto_setup: bool = parse_bool(
        os.getenv("CHECKPOINTER_POSTGRES_AUTO_SETUP", ""), True
    )
    rate_limit_enabled: bool = parse_bool(os.getenv("RATE_LIMIT_ENABLED", ""), False)
    redis_url: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    rate_limit_prefix: str = os.getenv("RATE_LIMIT_PREFIX", "rl")
    rate_limit_window_seconds: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    rate_limit_runs_per_window: int = int(
        os.getenv("RATE_LIMIT_RUNS_PER_WINDOW", "60")
    )
    prompt_cache_enabled: bool = parse_bool(os.getenv("PROMPT_CACHE_ENABLED", ""), False)
    prompt_cache_prefix: str = os.getenv("PROMPT_CACHE_PREFIX", "prompt_cache")
    prompt_cache_ttl_seconds: int = int(os.getenv("PROMPT_CACHE_TTL_SECONDS", "86400"))
    reviewer_cache_enabled: bool = parse_bool(os.getenv("REVIEWER_CACHE_ENABLED", ""), False)
    reviewer_cache_prefix: str = os.getenv("REVIEWER_CACHE_PREFIX", "reviewer_cache")
    reviewer_cache_ttl_seconds: int = int(os.getenv("REVIEWER_CACHE_TTL_SECONDS", "21600"))
    distributed_lock_enabled: bool = parse_bool(
        os.getenv("DISTRIBUTED_LOCK_ENABLED", ""),
        False,
    )
    distributed_lock_prefix: str = os.getenv(
        "DISTRIBUTED_LOCK_PREFIX",
        "distlock:run",
    )
    distributed_lock_ttl_seconds: int = int(
        os.getenv("DISTRIBUTED_LOCK_TTL_SECONDS", "900")
    )
    human_interrupt_hook_enabled: bool = parse_bool(
        os.getenv("HUMAN_INTERRUPT_HOOK_ENABLED", ""),
        False,
    )
    human_interrupt_hook_url: str = os.getenv("HUMAN_INTERRUPT_HOOK_URL", "")
    human_interrupt_hook_token: str = os.getenv("HUMAN_INTERRUPT_HOOK_TOKEN", "")
    human_interrupt_hook_timeout_seconds: float = float(
        os.getenv("HUMAN_INTERRUPT_HOOK_TIMEOUT_SECONDS", "2.0")
    )
    human_interrupt_hook_idempotency_ttl_seconds: int = int(
        os.getenv("HUMAN_INTERRUPT_HOOK_IDEMPOTENCY_TTL_SECONDS", "86400")
    )
    human_interrupt_hook_idempotency_prefix: str = os.getenv(
        "HUMAN_INTERRUPT_HOOK_IDEMPOTENCY_PREFIX",
        "hook:human_interrupt",
    )
    human_gate_max_rounds: int = int(os.getenv("HUMAN_GATE_MAX_ROUNDS", "3"))
    review_max_rounds: int = int(os.getenv("REVIEW_MAX_ROUNDS", "2"))
    coverage_min_evidence_hits: int = int(os.getenv("COVERAGE_MIN_EVIDENCE_HITS", "2"))
    coverage_min_confidence: float = float(os.getenv("COVERAGE_MIN_CONFIDENCE", "0.65"))
    coverage_blocking_confidence: float = float(os.getenv("COVERAGE_BLOCKING_CONFIDENCE", "0.75"))


settings = Settings()
