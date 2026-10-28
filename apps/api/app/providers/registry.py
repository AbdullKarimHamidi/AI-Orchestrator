import httpx

from app.providers.anthropic import AnthropicAdapter
from app.providers.base import ProviderAdapter, ProviderConfig
from app.providers.demo import DemoAdapter
from app.providers.gemini import GeminiAdapter
from app.providers.openai import OpenAIAdapter, OpenAICompatibleAdapter

_ADAPTERS = {
    "openai": OpenAIAdapter,
    "openai_compatible": OpenAICompatibleAdapter,
    "anthropic": AnthropicAdapter,
    "gemini": GeminiAdapter,
    "demo": DemoAdapter,
}

# Tests can install a transport (httpx.MockTransport) to exercise adapters offline.
test_transport: httpx.AsyncBaseTransport | None = None


def build_adapter(cfg: ProviderConfig) -> ProviderAdapter:
    cls = _ADAPTERS.get(cfg.kind)
    if cls is None:
        raise ValueError(f"unsupported provider kind {cfg.kind}")
    return cls(cfg, transport=test_transport)  # type: ignore[return-value]
