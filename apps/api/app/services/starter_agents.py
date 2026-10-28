"""Starter pack: ready-to-run agents on the best free provider the workspace has.

Agents run on the first available provider in PROVIDER_PREFERENCE, with the other free providers
as fallbacks (free tiers rate-limit, so a second provider keeps runs going). Without any free
provider they run on the Demo provider, and installing again after adding a key moves them
onto the real model. Agents the user has edited are never touched.
"""
from dataclasses import dataclass

from pymongo.asynchronous.database import AsyncDatabase

from app.core.exceptions import Conflict
from app.providers.demo import DEMO_MODELS
from app.repositories.agents import AgentRepository
from app.repositories.providers import ProviderRepository
from app.schemas.agents import AgentConfig, AgentCreate, AgentUpdate, ModelParams, ModelRef
from app.services.agents import AgentService
from app.services.providers import ProviderService

# Fast, generous free tiers first; local Ollama last because it depends on the user's machine.
PROVIDER_PREFERENCE = ["groq", "gemini", "cerebras", "openrouter", "mistral", "ollama"]


@dataclass(frozen=True)
class Starter:
    key: str
    name: str
    description: str
    system_prompt: str
    temperature: float = 0.4
    max_output_tokens: int = 1024


STARTERS: list[Starter] = [
    Starter("assistant", "General Assistant", "Everyday questions, explanations and planning.",
            "You are a helpful, accurate assistant. Answer clearly and concisely. If you are not sure, "
            "say so instead of guessing. Use short paragraphs or bullet points when they help.", 0.5),
    Starter("coder", "Code Helper", "Writes, explains, reviews and debugs code.",
            "You are a senior software engineer. Write correct, idiomatic, well-structured code. When "
            "fixing a bug, explain the cause in one or two sentences first. Put code in fenced blocks with "
            "the language name. Point out security or performance problems you notice.", 0.2, 2048),
    Starter("writer", "Writer & Editor", "Drafts and polishes emails, posts and documents.",
            "You are a professional writer and editor. Produce clear, natural text in the tone the user "
            "asks for (professional by default). When editing, keep the author's meaning and voice, and fix "
            "grammar, clarity and flow.", 0.7, 1500),
    Starter("summarizer", "Summarizer", "Turns long text into a short summary with key points.",
            "Summarize the text the user provides. Start with a one-sentence overview, then list the key "
            "points as bullets, then any action items or decisions. Never add facts that are not in the text.",
            0.2),
    Starter("translator", "Translator", "Translates between languages, including Persian/Dari and Arabic.",
            "You are an expert translator. Translate the user's text into the language they ask for; if they "
            "do not say, translate English into Persian (Dari) and any other language into English. Keep the "
            "meaning, tone and formatting. Output only the translation.", 0.2, 2048),
    Starter("support", "Customer Support", "Friendly first-line support replies.",
            "You are a friendly, patient customer support agent. Acknowledge the customer's issue, give "
            "clear step-by-step help, and ask for missing details when needed. Never invent policies, prices "
            "or promises; offer to escalate to a human instead.", 0.4),
    Starter("extractor", "Data Extractor", "Pulls structured JSON out of messy text.",
            "Extract the structured information the user asks for from the text they provide. Reply with "
            "valid JSON only, no commentary. Use null for anything that is not in the text.", 0.0),
    Starter("brainstorm", "Idea Generator", "Brainstorms names, ideas, plans and alternatives.",
            "You are a creative strategist. Generate varied, specific ideas, then briefly mark the two or "
            "three strongest and why. Be practical: prefer ideas someone could start on this week.", 0.9),
]

STARTER_NOTE = "Starter pack"


class StarterAgentService:
    def __init__(self, db: AsyncDatabase):
        self.agents = AgentService(db)
        self.agent_repo = AgentRepository(db)
        self.providers = ProviderRepository(db)
        self.provider_svc = ProviderService(db)

    async def model_chain(self, ws_id: str) -> list[ModelRef]:
        """Primary model plus up to three fallbacks, best free provider first, Demo last resort."""
        chain: list[ModelRef] = []
        for preset_id in PROVIDER_PREFERENCE:
            p = await self.providers.by_preset(ws_id, preset_id)
            if p and p.get("enabled", True) and p.get("health", {}).get("status") != "unhealthy":
                chain.append(ModelRef(provider_id=p["_id"], model=p["suggested_models"][0]))
        if not chain:
            demo = await self.providers.by_kind(ws_id, "demo")
            if demo:
                chain.append(ModelRef(provider_id=demo["_id"], model=DEMO_MODELS[0]))
        return chain[:4]

    def _config(self, s: Starter, chain: list[ModelRef]) -> AgentConfig:
        return AgentConfig(system_prompt=s.system_prompt, model=chain[0] if chain else None, fallbacks=chain[1:],
                           params=ModelParams(temperature=s.temperature, max_output_tokens=s.max_output_tokens))

    async def install(self, ws_id: str, user_id: str) -> dict:
        """Creates missing starter agents and moves untouched ones onto the current best providers.
        Returns the names created, updated and skipped (edited by the user, or name already taken)."""
        await self.provider_svc.ensure_demo(ws_id)
        await self.provider_svc.ensure_presets(ws_id)
        chain = await self.model_chain(ws_id)
        result: dict[str, list[str]] = {"created": [], "updated": [], "skipped": []}
        for s in STARTERS:
            cfg = self._config(s, chain)
            existing = await self.agent_repo.col.find_one({"workspace_id": ws_id, "starter": s.key, "deleted": False})
            if existing is None:
                try:
                    a = await self.agents.create(ws_id, user_id, AgentCreate(name=s.name, description=s.description,
                                                                             config=cfg))
                except Conflict:
                    result["skipped"].append(s.name)
                    continue
                await self.agent_repo.update(ws_id, a["_id"], {"starter": s.key})
                result["created"].append(s.name)
            else:
                # Only re-point agents whose prompt and params are still ours; never overwrite user edits.
                if existing["draft"].get("system_prompt") != s.system_prompt or existing["status"] == "retired":
                    result["skipped"].append(s.name)
                    continue
                new_cfg = cfg.model_dump(mode="json")
                if (existing["draft"].get("model"), existing["draft"].get("fallbacks")) == (
                        new_cfg["model"], new_cfg["fallbacks"]):
                    continue
                a = await self.agents.update(ws_id, user_id, existing["_id"], AgentUpdate(
                    revision=existing["revision"], config=AgentConfig.model_validate(
                        existing["draft"] | {"model": new_cfg["model"], "fallbacks": new_cfg["fallbacks"]})))
                result["updated"].append(s.name)
            if chain and a["status"] != "paused":
                try:
                    await self.agents.publish(ws_id, user_id, a["_id"], STARTER_NOTE)
                except Conflict:
                    pass  # nothing changed since the last publish
        return result
