"""Minimal Model Context Protocol client over Streamable HTTP (JSON-RPC 2.0).

Supports what agents need: initialize, tools/list, tools/call. Servers may answer a POST with
plain JSON or with a short Server-Sent Events stream; both are handled. A session id returned by
the server (Mcp-Session-Id) is sent on later requests.
"""
import json
from itertools import count

import httpx

from app.core.config import get_settings
from app.tools import http_tool
from app.tools.http_tool import ToolExecutionError, assert_public_host

PROTOCOL_VERSION = "2025-06-18"


class McpClient:
    def __init__(self, url: str, headers: dict[str, str] | None = None, timeout: float | None = None):
        self.url = url
        self.headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
                        **(headers or {})}
        self.timeout = timeout or get_settings().tool_timeout_seconds
        self._ids = count(1)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "McpClient":
        await assert_public_host(self.url)
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=10.0), follow_redirects=False,
                                         transport=http_tool.test_transport)
        await self._rpc("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                       "clientInfo": {"name": "orchestrator", "version": "1"}})
        await self._notify("notifications/initialized")
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()

    async def _post(self, payload: dict) -> httpx.Response:
        assert self._client is not None
        try:
            resp = await self._client.post(self.url, json=payload, headers=self.headers)
        except httpx.TimeoutException as exc:
            raise ToolExecutionError(f"MCP server timed out after {self.timeout}s") from exc
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"MCP network error: {type(exc).__name__}") from exc
        if sid := resp.headers.get("mcp-session-id"):
            self.headers["Mcp-Session-Id"] = sid
        if resp.status_code >= 400:
            raise ToolExecutionError(f"MCP server returned HTTP {resp.status_code}: {resp.text[:500]}")
        return resp

    async def _notify(self, method: str) -> None:
        await self._post({"jsonrpc": "2.0", "method": method})

    async def _rpc(self, method: str, params: dict) -> dict:
        rid = next(self._ids)
        resp = await self._post({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        msg = _find_response(resp, rid)
        if "error" in msg:
            err = msg["error"] or {}
            raise ToolExecutionError(f"MCP error {err.get('code')}: {err.get('message')}")
        return msg.get("result") or {}

    async def list_tools(self) -> list[dict]:
        tools: list[dict] = []
        cursor = None
        for _ in range(20):  # pagination guard
            res = await self._rpc("tools/list", {"cursor": cursor} if cursor else {})
            tools += res.get("tools") or []
            cursor = res.get("nextCursor")
            if not cursor:
                break
        return tools

    async def call_tool(self, name: str, arguments: dict) -> str:
        res = await self._rpc("tools/call", {"name": name, "arguments": arguments})
        parts = []
        for c in res.get("content") or []:
            if c.get("type") == "text":
                parts.append(c.get("text", ""))
            elif c.get("type") == "resource":
                parts.append(json.dumps(c.get("resource"))[:5000])
            else:
                parts.append(f"[{c.get('type')} content omitted]")
        if res.get("structuredContent") is not None and not parts:
            parts.append(json.dumps(res["structuredContent"]))
        text = "\n".join(parts)[: get_settings().tool_max_response_bytes]
        if res.get("isError"):
            raise ToolExecutionError(text or "MCP tool reported an error")
        return text


def _find_response(resp: httpx.Response, rid: int) -> dict:
    ctype = resp.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        for block in resp.text.split("\n\n"):
            data = "\n".join(line[5:].strip() for line in block.splitlines() if line.startswith("data:"))
            if not data:
                continue
            try:
                msg = json.loads(data)
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("id") == rid:
                return msg
        raise ToolExecutionError("MCP server stream ended without a response")
    try:
        msg = resp.json()
    except ValueError as exc:
        raise ToolExecutionError("MCP server returned non-JSON") from exc
    if isinstance(msg, list):
        msg = next((m for m in msg if isinstance(m, dict) and m.get("id") == rid), {})
    return msg if isinstance(msg, dict) else {}
