"""Ollama: models running on your own machine (https://ollama.com).

Chat goes through Ollama's OpenAI-compatible ``/v1/chat/completions`` endpoint (tool calling
included); the model list comes from the native ``/api/tags`` endpoint, which returns exactly the
models that have been pulled. The base URL is the server root, e.g. ``http://localhost:11434``;
a URL that already ends in ``/v1`` or ``/api`` is accepted and normalized.
"""
import os

from app.providers.base import ChatRequest, ChatResult, ProviderError
from app.providers.openai import OpenAICompatibleAdapter

OLLAMA_LOCAL_URL = "http://localhost:11434"
OLLAMA_DOCKER_URL = "http://host.docker.internal:11434"


def running_in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def default_ollama_url() -> str:
    """Where Ollama usually is from this process: the host machine when we run inside Docker."""
    return OLLAMA_DOCKER_URL if running_in_docker() else OLLAMA_LOCAL_URL


def normalize_ollama_url(url: str | None) -> str:
    """Server root without a trailing slash, ``/v1`` or ``/api`` (users paste any of these)."""
    u = (url or default_ollama_url()).strip().rstrip("/")
    for suffix in ("/v1", "/api"):
        if u.endswith(suffix):
            u = u[: -len(suffix)]
    return u.rstrip("/") or default_ollama_url()


def _hint(root: str) -> str:
    if running_in_docker() and ("localhost" in root or "127.0.0.1" in root):
        return (f" Inside Docker, localhost is the container itself: use {OLLAMA_DOCKER_URL} and start Ollama "
                "with OLLAMA_HOST=0.0.0.0.")
    return " Is Ollama running? Start it with `ollama serve` (or open the Ollama app)."


class OllamaAdapter(OpenAICompatibleAdapter):
    kind = "ollama"
    default_base = OLLAMA_LOCAL_URL

    @property
    def root(self) -> str:
        return normalize_ollama_url(self.cfg.base_url)

    @property
    def base(self) -> str:
        return f"{self.root}/v1"

    def _friendly(self, exc: ProviderError, model: str | None = None) -> ProviderError:
        if exc.kind in ("unavailable", "timeout") and exc.status is None:
            return ProviderError(exc.kind, f"cannot reach Ollama at {self.root} ({exc.message}).{_hint(self.root)}")
        if exc.kind == "not_found" and model:
            return ProviderError("not_found", f"model '{model}' is not installed in Ollama. "
                                              f"Run: ollama pull {model}", exc.status)
        return exc

    async def chat(self, req: ChatRequest) -> ChatResult:
        try:
            return await super().chat(req)
        except ProviderError as exc:
            raise self._friendly(exc, req.model) from exc

    async def list_models(self) -> list[str]:
        try:
            data = await self._request("GET", f"{self.root}/api/tags", headers=self._headers())
        except ProviderError as exc:
            if exc.kind != "not_found":
                raise self._friendly(exc) from exc
            return await super().list_models()  # a proxy that only exposes the OpenAI API
        names = [m.get("name") or m.get("model") for m in data.get("models", []) if isinstance(m, dict)]
        return sorted(n for n in names if n)
