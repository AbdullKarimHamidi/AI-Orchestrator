"""Tool registry and runtime.

A tool is a workspace-level definition (HTTP endpoint or a tool on an MCP server) with a JSON
Schema for its arguments. Agents opt in per tool (``config.tool_ids``); the executor offers only
those tools to the model, validates every call against the schema, executes it, and records
``tool.call`` / ``tool.result`` events. Secret headers are encrypted at rest and never returned.
"""
from __future__ import annotations

import json
import time

import jsonschema
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import Conflict, NotFound
from app.core.ids import new_id
from app.core.logging import redact_text
from app.core.security import get_cipher
from app.repositories.audit import AuditRepository
from app.repositories.base import now
from app.repositories.tools import ToolRepository
from app.schemas.tools import McpImportRequest, ToolCreate, ToolUpdate
from app.tools.http_tool import ToolExecutionError, call_http_tool
from app.tools.mcp import McpClient

KNOWLEDGE_TOOL = "knowledge_search"


def present_tool(t: dict) -> dict:
    return {"id": t["_id"], "name": t["name"], "description": t["description"], "kind": t["kind"],
            "input_schema": t["input_schema"], "http": t.get("http"), "mcp": t.get("mcp"),
            "headers": t.get("headers") or {}, "secret_header_names": t.get("secret_header_names") or [],
            "enabled": t.get("enabled", True), "created_at": t["created_at"],
            "updated_at": t.get("updated_at", t["created_at"])}


def _encrypt_headers(h: dict[str, str]) -> dict:
    if not h:
        return {"secret_headers_enc": None, "secret_header_names": []}
    return {"secret_headers_enc": get_cipher().encrypt(json.dumps(h)), "secret_header_names": sorted(h)}


def secret_headers(t: dict) -> dict[str, str]:
    enc = t.get("secret_headers_enc")
    return json.loads(get_cipher().decrypt(enc)) if enc else {}


async def execute_tool(t: dict, args: dict) -> str:
    """Runs one tool call. Raises ToolExecutionError for anything the model should see as an error."""
    if not t.get("enabled", True):
        raise ToolExecutionError(f"tool {t['name']} is disabled")
    try:
        jsonschema.validate(args, t["input_schema"])
    except jsonschema.ValidationError as exc:
        raise ToolExecutionError(f"invalid arguments: {exc.message}") from exc
    try:
        headers = secret_headers(t)
    except ValueError as exc:
        raise ToolExecutionError("tool credentials cannot be decrypted (ENCRYPTION_KEYS changed?)") from exc
    if t["kind"] == "http":
        return await call_http_tool(t["http"], headers, args)
    async with McpClient(t["mcp"]["server_url"], {**(t.get("headers") or {}), **headers},
                         timeout=(t.get("http") or {}).get("timeout_seconds")) as c:
        return await c.call_tool(t["mcp"]["tool_name"], args)


class ToolService:
    def __init__(self, db: AsyncDatabase):
        self.repo = ToolRepository(db)
        self.audit = AuditRepository(db)

    async def get(self, ws_id: str, tool_id: str) -> dict:
        t = await self.repo.get(ws_id, tool_id)
        if not t:
            raise NotFound("Tool not found")
        return t

    async def list(self, ws_id: str) -> list[dict]:
        items, _ = await self.repo.list(ws_id, {"deleted": False}, sort=[("name_lower", 1)], limit=500)
        return items

    async def create(self, ws_id: str, user_id: str, req: ToolCreate) -> dict:
        if req.name.lower() == KNOWLEDGE_TOOL:
            raise Conflict(f"'{KNOWLEDGE_TOOL}' is reserved for knowledge bases", code="NAME_RESERVED")
        t = now()
        doc = {"_id": new_id("tol"), "workspace_id": ws_id, "name": req.name, "name_lower": req.name.lower(),
               "description": req.description, "kind": req.kind, "input_schema": req.input_schema,
               "http": req.http.model_dump(mode="json") if req.http else None,
               "mcp": req.mcp.model_dump(mode="json") if req.mcp else None,
               "headers": req.headers, **_encrypt_headers(req.secret_headers), "enabled": req.enabled,
               "created_by": user_id, "created_at": t, "updated_at": t, "deleted": False}
        try:
            await self.repo.insert(doc)
        except DuplicateKeyError as exc:
            raise Conflict("A tool with this name already exists", code="NAME_TAKEN") from exc
        await self.audit.record(ws_id, user_id, "tool.create", "tool", doc["_id"], {"kind": req.kind})
        return doc

    async def update(self, ws_id: str, user_id: str, tool_id: str, req: ToolUpdate) -> dict:
        cur = await self.get(ws_id, tool_id)
        data = req.model_dump(exclude_unset=True, mode="json")
        fields: dict = {}
        if "name" in data:
            if data["name"].lower() == KNOWLEDGE_TOOL:
                raise Conflict(f"'{KNOWLEDGE_TOOL}' is reserved for knowledge bases", code="NAME_RESERVED")
            fields |= {"name": data["name"], "name_lower": data["name"].lower()}
        for k in ("description", "input_schema", "headers", "enabled"):
            if k in data and data[k] is not None:
                fields[k] = data[k]
        if data.get("http") and cur["kind"] == "http":
            fields["http"] = data["http"]
        if data.get("mcp") and cur["kind"] == "mcp":
            fields["mcp"] = data["mcp"]
        if req.secret_headers is not None:
            fields |= _encrypt_headers(req.secret_headers)
        try:
            updated = await self.repo.update(ws_id, tool_id, fields)
        except DuplicateKeyError as exc:
            raise Conflict("A tool with this name already exists", code="NAME_TAKEN") from exc
        await self.audit.record(ws_id, user_id, "tool.update", "tool", tool_id,
                                {"fields": sorted(k for k in fields if k != "secret_headers_enc")})
        return updated  # type: ignore[return-value]

    async def delete(self, ws_id: str, user_id: str, tool_id: str) -> None:
        await self.get(ws_id, tool_id)
        await self.repo.update(ws_id, tool_id, {"deleted": True, "name_lower": f"{tool_id}:deleted"})
        await self.audit.record(ws_id, user_id, "tool.delete", "tool", tool_id)

    async def test(self, ws_id: str, user_id: str, tool_id: str, args: dict) -> dict:
        t = await self.get(ws_id, tool_id)
        started = time.monotonic()
        try:
            out, err = await execute_tool({**t, "enabled": True}, args), None
        except ToolExecutionError as exc:
            out, err = None, redact_text(str(exc))
        await self.audit.record(ws_id, user_id, "tool.test", "tool", tool_id, {"ok": err is None})
        return {"ok": err is None, "output": out, "error": err, "latency_ms": int((time.monotonic() - started) * 1000)}

    @staticmethod
    async def discover_mcp(server_url: str, headers: dict[str, str]) -> list[dict]:
        async with McpClient(server_url, headers) as c:
            tools = await c.list_tools()
        return [{"name": t.get("name", ""), "description": t.get("description") or "",
                 "input_schema": t.get("inputSchema") or {"type": "object", "properties": {}}}
                for t in tools if t.get("name")]

    async def import_mcp(self, ws_id: str, user_id: str, req: McpImportRequest) -> list[dict]:
        url = str(req.server_url)
        try:
            remote = {t["name"]: t for t in await self.discover_mcp(url, req.secret_headers)}
        except ToolExecutionError as exc:
            raise Conflict(f"Could not reach the MCP server: {exc}", code="MCP_UNREACHABLE") from exc
        missing = [n for n in req.tools if n not in remote]
        if missing:
            raise NotFound(f"Not offered by the server: {', '.join(missing)}", code="MCP_TOOL_NOT_FOUND")
        created = []
        for n in req.tools:
            r = remote[n]
            local = (req.name_prefix + n)[:64]
            local = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in local)
            if not local[0].isalpha():
                local = "t" + local[:63]
            created.append(await self.create(ws_id, user_id, ToolCreate(
                name=local, description=(r["description"] or n)[:4000], kind="mcp",
                input_schema=r["input_schema"] if r["input_schema"].get("type", "object") == "object"
                else {"type": "object", "properties": {}},
                mcp={"server_url": url, "tool_name": n}, secret_headers=req.secret_headers)))
        return created
