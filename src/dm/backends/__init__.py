"""LLM backend factory — lazy imports keep optional deps optional."""
from __future__ import annotations

from src.dm.backends.base import LLMBackend

_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-6",
    "gemini": "gemini-2.0-flash",
    "ollama": "llama3.2",
    "deepseek": "deepseek-chat",
}

PROVIDERS = list(_DEFAULT_MODELS)


def create_backend(provider: str, model: str | None = None) -> LLMBackend:
    """Instantiate the requested backend, applying per-provider defaults."""
    m = model or _DEFAULT_MODELS.get(provider, "")
    if provider == "anthropic":
        from src.dm.backends.anthropic_backend import AnthropicBackend
        return AnthropicBackend(m)
    elif provider == "gemini":
        from src.dm.backends.gemini import GeminiBackend
        return GeminiBackend(m)
    elif provider == "ollama":
        from src.dm.backends.ollama import OllamaBackend
        return OllamaBackend(m)
    elif provider == "deepseek":
        from src.dm.backends.deepseek import DeepSeekBackend
        return DeepSeekBackend(m)
    else:
        raise ValueError(
            f"Unknown provider: {provider!r}. Choose from: {', '.join(PROVIDERS)}"
        )


__all__ = ["LLMBackend", "create_backend", "PROVIDERS"]
