from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from app.config import settings
from app.services.runtime_settings import get_runtime_settings

AGENT_MODEL_OVERRIDES = {
    "requirement": "requirement_llm_model",
    "feasibility": "feasibility_llm_model",
    "architect": "architect_llm_model",
    "planner": "planner_llm_model",
    "prompt_builder": "prompt_builder_llm_model",
    "reviewer": "reviewer_llm_model",
}


def _default_model_for(provider: str) -> str:
    runtime = get_runtime_settings(reveal_secrets=True)
    defaults = {
        "openai": "gpt-5",
        "azure_openai": runtime.get("azure_openai_deployment") or "gpt-4o",
        "anthropic": "claude-3-5-sonnet-latest",
        "google": "gemini-2.0-flash",
        "google_genai": "gemini-2.0-flash",
        "ollama": "qwen2.5:7b",
        "openrouter": "openai/gpt-4o-mini",
    }
    return defaults.get(provider, "gpt-5")


def _resolve_model(provider: str, agent_key: str | None = None) -> str:
    runtime = get_runtime_settings(reveal_secrets=True)
    if agent_key:
        attr_name = AGENT_MODEL_OVERRIDES.get(agent_key)
        if attr_name:
            override = str(runtime.get(attr_name, "") or "")
            if override and override.strip():
                return override.strip()
    model = str(runtime.get("llm_model", "") or "").strip()
    if model:
        return model
    return _default_model_for(provider)


def _is_dashscope_base_url(url: str) -> bool:
    return "dashscope" in (url or "").lower()


def _openai_extra_body(provider: str, model: str) -> dict:
    runtime = get_runtime_settings(reveal_secrets=True)
    extra_body: dict = {}
    if runtime.get("llm_enable_thinking") is not None:
        extra_body["enable_thinking"] = runtime.get("llm_enable_thinking")
        return extra_body

    # DashScope Qwen models may reject tool_choice=required in thinking mode.
    # LangChain agents commonly force tool_choice when tools/structured output are enabled.
    # We disable thinking by default in this specific combination for compatibility.
    if provider == "openai" and _is_dashscope_base_url(str(runtime.get("openai_base_url", ""))):
        if model.lower().startswith("qwen"):
            extra_body["enable_thinking"] = False
    return extra_body


def get_llm(agent_key: str | None = None) -> BaseChatModel:
    runtime = get_runtime_settings(reveal_secrets=True)
    provider = str(runtime.get("llm_provider", settings.llm_provider)).lower().strip()
    model = _resolve_model(provider, agent_key=agent_key)
    temperature = float(runtime.get("llm_temperature", settings.llm_temperature))

    if provider == "openai":
        extra_body = _openai_extra_body(provider, model)
        return ChatOpenAI(
            api_key=str(runtime.get("openai_api_key", "") or ""),
            base_url=str(runtime.get("openai_base_url", "") or "") or None,
            model=model,
            temperature=temperature,
            extra_body=extra_body or None,
        )

    if provider == "azure_openai":
        return AzureChatOpenAI(
            api_key=str(runtime.get("azure_openai_api_key", "") or "")
            or str(runtime.get("openai_api_key", "") or ""),
            azure_endpoint=str(runtime.get("azure_openai_endpoint", "") or ""),
            azure_deployment=str(runtime.get("azure_openai_deployment", "") or "") or model,
            api_version=str(runtime.get("azure_openai_api_version", "") or settings.azure_openai_api_version),
            temperature=temperature,
        )

    if provider == "openrouter":
        extra_body = _openai_extra_body(provider, model)
        return ChatOpenAI(
            api_key=str(runtime.get("openrouter_api_key", "") or "")
            or str(runtime.get("openai_api_key", "") or ""),
            base_url=str(runtime.get("openrouter_base_url", "") or settings.openrouter_base_url),
            model=model,
            temperature=temperature,
            extra_body=extra_body or None,
        )

    if provider in {"google", "google_genai"}:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise ImportError(
                "Missing dependency for Google GenAI. Install `langchain-google-genai`."
            ) from exc
        return ChatGoogleGenerativeAI(
            google_api_key=str(runtime.get("google_api_key", "") or ""),
            model=model,
            temperature=temperature,
        )

    if provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise ImportError(
                "Missing dependency for Anthropic. Install `langchain-anthropic`."
            ) from exc
        return ChatAnthropic(
            api_key=str(runtime.get("anthropic_api_key", "") or ""),
            model=model,
            temperature=temperature,
        )

    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise ImportError(
                "Missing dependency for Ollama. Install `langchain-ollama`."
            ) from exc
        return ChatOllama(
            base_url=str(runtime.get("ollama_base_url", "") or settings.ollama_base_url),
            model=model,
            temperature=temperature,
        )

    raise ValueError(
        "Unsupported LLM_PROVIDER. Use one of: "
        "openai, azure_openai, anthropic, google, ollama, openrouter."
    )
