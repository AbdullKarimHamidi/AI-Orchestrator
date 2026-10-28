"""HTTP tools: the model's arguments become path placeholders, query parameters or a JSON body.

Safety:
- Only http(s). Targets that resolve to private, loopback, link-local, reserved or multicast
  addresses are refused unless TOOLS_ALLOW_PRIVATE_NETWORKS=true (SSRF protection; covers cloud
  metadata endpoints such as 169.254.169.254).
- No redirects are followed (a redirect could point at a blocked address).
- Responses are capped at TOOL_MAX_RESPONSE_BYTES; secrets in headers never reach the model or logs.
"""
import asyncio
import ipaddress
import json
import re
import socket
from urllib.parse import quote, urlsplit

import httpx

from app.core.config import get_settings

PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

# Tests can install an httpx.MockTransport here (and skip DNS checks).
test_transport: httpx.AsyncBaseTransport | None = None


class ToolExecutionError(Exception):
    """Raised for failures the model should see as a tool error (not a run failure)."""


async def assert_public_host(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ToolExecutionError("only http(s) URLs with a host are allowed")
    if get_settings().tools_allow_private_networks or test_transport is not None:
        return
    host = parts.hostname
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, parts.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ToolExecutionError(f"cannot resolve host {host}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
                or ip.is_unspecified):
            raise ToolExecutionError(
                f"{host} resolves to a private address ({ip}); set TOOLS_ALLOW_PRIVATE_NETWORKS=true to allow it")


def render_request(cfg: dict, args: dict) -> tuple[str, str, dict | None, dict | None]:
    """Returns (method, url, query, json_body). Placeholders in the URL consume their arguments;
    the rest go to the query string (GET/DELETE) or the JSON body (POST/PUT/PATCH)."""
    method = cfg.get("method", "GET").upper()
    used: set[str] = set()

    def sub(m: re.Match) -> str:
        name = m.group(1)
        if name not in args:
            raise ToolExecutionError(f"missing argument '{name}' for the URL")
        used.add(name)
        return quote(str(args[name]), safe="")

    url = PLACEHOLDER.sub(sub, cfg["url"])
    rest = {k: v for k, v in args.items() if k not in used}
    if method in ("GET", "DELETE"):
        query = {k: v if isinstance(v, str | int | float) else json.dumps(v) for k, v in rest.items()}
        return method, url, query or None, None
    return method, url, None, rest


async def call_http_tool(cfg: dict, secret_headers: dict[str, str], args: dict) -> str:
    s = get_settings()
    method, url, query, body = render_request(cfg, args)
    await assert_public_host(url)
    headers = {"User-Agent": "orchestrator-tools/1", **(cfg.get("headers") or {}), **secret_headers}
    timeout = float(cfg.get("timeout_seconds") or s.tool_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0), follow_redirects=False,
                                     transport=test_transport) as c:
            async with c.stream(method, url, params=query, json=body, headers=headers) as resp:
                chunks, size = [], 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    chunks.append(chunk)
                    if size > s.tool_max_response_bytes:
                        break
                raw = b"".join(chunks)[: s.tool_max_response_bytes]
    except httpx.TimeoutException as exc:
        raise ToolExecutionError(f"tool timed out after {timeout}s") from exc
    except httpx.HTTPError as exc:
        raise ToolExecutionError(f"network error: {type(exc).__name__}") from exc
    text = raw.decode(resp.encoding or "utf-8", errors="replace")
    truncated = " [truncated]" if size > s.tool_max_response_bytes else ""
    if resp.status_code >= 400:
        raise ToolExecutionError(f"HTTP {resp.status_code}: {text[:2000]}{truncated}")
    return text + truncated
