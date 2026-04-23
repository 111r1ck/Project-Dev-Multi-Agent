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
    human_gate_max_rounds: int = int(os.getenv("HUMAN_GATE_MAX_ROUNDS", "3"))


settings = Settings()
