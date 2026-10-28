"""Embedding adapters. A knowledge base either uses a provider's embedding model (OpenAI,
Gemini, any OpenAI-compatible server) or, with no embedding model, the built-in lexical vectors
(feature hashing of words; offline and free, good for keyword-style questions)."""
import hashlib
import math
import re
from urllib.parse import quote

import numpy as np

from app.providers.base import HttpAdapter, ProviderConfig, ProviderError

LEXICAL_DIM = 512
_WORD = re.compile(r"[\w']+", re.UNICODE)
BATCH = 64


_STOP = frozenset("""a an and are as at be by can do does for from has have how i if in is it its me my of on or our
so that the their this to was we what when where which who why will with you your""".split())
_SUFFIXES = ("ing", "ies", "es", "ed", "s")


def _stem(w: str) -> str:
    """Crude suffix stripping so "refunds"/"refund" and "shipping"/"ship" share a feature."""
    for suf in _SUFFIXES:
        if len(w) > len(suf) + 3 and w.endswith(suf):
            w = w[: -len(suf)] + ("y" if suf == "ies" else "")
            break
    if len(w) > 4 and w[-1] == w[-2] and w[-1] not in "aeiou":  # shipp -> ship
        w = w[:-1]
    return w


def lexical_vector(text: str) -> list[float]:
    v = np.zeros(LEXICAL_DIM, dtype=np.float32)
    words = [_stem(w) for w in (t.lower() for t in _WORD.findall(text)) if w not in _STOP]
    for w in words + [f"{a} {b}" for a, b in zip(words, words[1:], strict=False)]:
        h = int.from_bytes(hashlib.blake2b(w.encode(), digest_size=8).digest(), "big")
        v[h % LEXICAL_DIM] += 1.0 if (h >> 63) & 1 else -1.0
    v = np.sign(v) * np.log1p(np.abs(v))
    n = float(np.linalg.norm(v))
    return (v / n).tolist() if n else v.tolist()


class _OpenAIEmbeddings(HttpAdapter):
    default_base = "https://api.openai.com/v1"

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        base = (self.cfg.base_url or self.default_base).rstrip("/")
        headers = {"Content-Type": "application/json"}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"
        data = await self._request("POST", f"{base}/embeddings", headers=headers, json={"model": model, "input": texts})
        rows = sorted(data.get("data") or [], key=lambda r: r.get("index", 0))
        return [r["embedding"] for r in rows]


class _GeminiEmbeddings(HttpAdapter):
    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        base = (self.cfg.base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        m = model.removeprefix("models/")
        data = await self._request(
            "POST", f"{base}/models/{quote(m, safe='')}:batchEmbedContents",
            headers={"x-goog-api-key": self.cfg.api_key or "", "Content-Type": "application/json"},
            json={"requests": [{"model": f"models/{m}", "content": {"parts": [{"text": t}]}} for t in texts]})
        return [e["values"] for e in data.get("embeddings") or []]


def _normalize(rows: list[list[float]]) -> list[list[float]]:
    out = []
    for r in rows:
        n = math.sqrt(sum(x * x for x in r)) or 1.0
        out.append([x / n for x in r])
    return out


async def embed_texts(cfg: ProviderConfig | None, model: str | None, texts: list[str]) -> list[list[float]]:
    """Unit-normalized vectors. ``cfg`` None means the built-in lexical embedding."""
    if cfg is None or cfg.kind == "demo" or not model:
        return [lexical_vector(t) for t in texts]
    if cfg.kind in ("openai", "openai_compatible"):
        client = _OpenAIEmbeddings(cfg)
    elif cfg.kind == "gemini":
        client = _GeminiEmbeddings(cfg)  # type: ignore[assignment]
    else:
        raise ProviderError("bad_request", f"provider kind {cfg.kind} has no embeddings API")
    vectors: list[list[float]] = []
    for i in range(0, len(texts), BATCH):
        batch = await client.embed(model, texts[i:i + BATCH])
        if len(batch) != len(texts[i:i + BATCH]):
            raise ProviderError("unknown", "embedding response size mismatch")
        vectors += batch
    return _normalize(vectors)
