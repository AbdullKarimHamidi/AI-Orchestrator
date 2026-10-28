from fastapi import APIRouter, Depends

from app.api.deps import Ctx, db_dep, require
from app.core.exceptions import Conflict
from app.schemas.tools import (
    McpDiscoverRequest,
    McpImportRequest,
    McpRemoteTool,
    ToolCreate,
    ToolOut,
    ToolTestOut,
    ToolTestRequest,
    ToolUpdate,
)
from app.services.tools import ToolService, present_tool
from app.tools.http_tool import ToolExecutionError

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=list[ToolOut])
async def list_tools(ctx: Ctx = Depends(require("tools:read")), db=Depends(db_dep)):
    return [present_tool(t) for t in await ToolService(db).list(ctx.workspace_id)]


@router.post("", response_model=ToolOut, status_code=201)
async def create_tool(body: ToolCreate, ctx: Ctx = Depends(require("tools:write")), db=Depends(db_dep)):
    return present_tool(await ToolService(db).create(ctx.workspace_id, ctx.user_id, body))


@router.post("/mcp/discover", response_model=list[McpRemoteTool])
async def discover_mcp(body: McpDiscoverRequest, _: Ctx = Depends(require("tools:write"))):
    """Lists the tools an MCP server (Streamable HTTP) offers, without saving anything."""
    try:
        return await ToolService.discover_mcp(str(body.server_url), body.secret_headers)
    except ToolExecutionError as exc:
        raise Conflict(f"Could not reach the MCP server: {exc}", code="MCP_UNREACHABLE") from exc


@router.post("/mcp/import", response_model=list[ToolOut], status_code=201)
async def import_mcp(body: McpImportRequest, ctx: Ctx = Depends(require("tools:write")), db=Depends(db_dep)):
    return [present_tool(t) for t in await ToolService(db).import_mcp(ctx.workspace_id, ctx.user_id, body)]


@router.get("/{tool_id}", response_model=ToolOut)
async def get_tool(tool_id: str, ctx: Ctx = Depends(require("tools:read")), db=Depends(db_dep)):
    return present_tool(await ToolService(db).get(ctx.workspace_id, tool_id))


@router.patch("/{tool_id}", response_model=ToolOut)
async def update_tool(tool_id: str, body: ToolUpdate, ctx: Ctx = Depends(require("tools:write")),
                      db=Depends(db_dep)):
    return present_tool(await ToolService(db).update(ctx.workspace_id, ctx.user_id, tool_id, body))


@router.delete("/{tool_id}", status_code=204)
async def delete_tool(tool_id: str, ctx: Ctx = Depends(require("tools:write")), db=Depends(db_dep)):
    await ToolService(db).delete(ctx.workspace_id, ctx.user_id, tool_id)


@router.post("/{tool_id}/test", response_model=ToolTestOut)
async def test_tool(tool_id: str, body: ToolTestRequest, ctx: Ctx = Depends(require("tools:write")),
                    db=Depends(db_dep)):
    """Executes the tool once with the given arguments (a real call to the target)."""
    return await ToolService(db).test(ctx.workspace_id, ctx.user_id, tool_id, body.arguments)
