"""Ready-made connections for AI APIs with a free tier, plus local Ollama.

Each preset maps onto an existing adapter kind, so no new wire format is involved. A preset
whose key (or, for Ollama, base URL) is set in the environment is added to every workspace
automatically; the others can be added from the Models page by pasting a key.

Free model lineups change often, so ``models`` are suggestions for the model picker, not an
allowlist: the agent form offers them, and "Test connection" lists what the account really has.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    kind: str
    base_url: str | None
    env_key: str  # Settings attribute that holds the key (or base URL for Ollama)
    models: list[str]
    signup_url: str
    free_tier: str
    needs_key: bool = True
    timeout_seconds: int = 60

    @property
    def default_model(self) -> str:
        return self.models[0]


FREE_PRESETS: list[Preset] = [
    Preset(id="groq", name="Groq (free tier)", kind="openai_compatible",
           base_url="https://api.groq.com/openai/v1", env_key="groq_api_key",
           models=["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b", "openai/gpt-oss-20b"],
           signup_url="https://console.groq.com/keys",
           free_tier="Free plan with per-minute and per-day request limits, no card needed. Very fast."),
    Preset(id="gemini", name="Google Gemini (free tier)", kind="gemini", base_url=None, env_key="gemini_api_key",
           models=["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"],
           signup_url="https://aistudio.google.com/apikey",
           free_tier="Free tier in Google AI Studio with daily request limits, no card needed."),
    Preset(id="cerebras", name="Cerebras (free tier)", kind="openai_compatible",
           base_url="https://api.cerebras.ai/v1", env_key="cerebras_api_key",
           models=["gpt-oss-120b", "llama3.1-8b", "qwen-3-32b"],
           signup_url="https://cloud.cerebras.ai/",
           free_tier="Free plan with daily token limits, no card needed."),
    Preset(id="openrouter", name="OpenRouter (free models)", kind="openai_compatible",
           base_url="https://openrouter.ai/api/v1", env_key="openrouter_api_key",
           models=["meta-llama/llama-3.3-70b-instruct:free", "deepseek/deepseek-r1-0528:free",
                   "qwen/qwen3-coder:free", "mistralai/mistral-small-3.2-24b-instruct:free"],
           signup_url="https://openrouter.ai/keys",
           free_tier="Models ending in ':free' cost nothing; daily request cap applies. Free list changes, "
                     "use Test connection to see the current one."),
    Preset(id="mistral", name="Mistral (free Experiment plan)", kind="openai_compatible",
           base_url="https://api.mistral.ai/v1", env_key="mistral_api_key",
           models=["mistral-small-latest", "open-mistral-nemo", "codestral-latest"],
           signup_url="https://console.mistral.ai/api-keys",
           free_tier="Free 'Experiment' plan after phone verification, rate limited."),
    Preset(id="ollama", name="Ollama (local, free)", kind="openai_compatible",
           base_url="http://localhost:11434/v1", env_key="ollama_base_url",
           models=["llama3.2", "qwen2.5", "mistral", "gemma3"], signup_url="https://ollama.com/download",
           free_tier="Runs models on your own machine: free and unlimited. Install Ollama, then "
                     "run: ollama pull llama3.2", needs_key=False, timeout_seconds=300),
]

PRESETS_BY_ID = {p.id: p for p in FREE_PRESETS}
