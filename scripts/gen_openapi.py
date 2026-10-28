"""Generates companions/openapi.yaml — the reference API contract for the platform.

The FastAPI application is the source of truth; this file is the pre-implementation
reference contract derived from the blueprint's route inventory.
"""
import yaml


def REF(name):
    return {"$ref": f"#/components/responses/{name}"}


def P(name, where="query", **kw):
    d = {"name": name, "in": where}
    if "required" not in kw:
        d["required"] = where == "path"
    typ = kw.pop("type", None)
    d.update(kw)
    if typ is not None and "schema" not in d:
        d["schema"] = {"type": typ}
    if "schema" not in d and "content" not in d:
        d["schema"] = {"type": "string"}
    return d


def path_param(n):
    return P(n, "path", required=True, schema={"type": "string"})


def body(props, required=None):
    return {"type": "object", "properties": props, "required": list(props) if required is None else required}


def resolve_resp(name):
    """Map a resource name to an envelope-wrapped response schema (§19.1: {data: T})."""
    if name == "Envelope":
        return {"$ref": "#/components/schemas/Envelope"}
    if name.endswith("List"):
        base = name[:-4]
        return {"allOf": [{"$ref": "#/components/schemas/Envelope"},
                {"type": "object", "properties": {
                    "data": {"type": "object", "required": ["items"],
                            "properties": {"items": {"type": "array", "items": {"$ref": f"#/components/schemas/{base}"}}}},
                    "meta": {"type": "object", "required": ["next_cursor"],
                            "properties": {"next_cursor": {"type": ["string", "null"]}}}}}]}
    return {"allOf": [{"$ref": "#/components/schemas/Envelope"},
            {"type": "object", "properties": {"data": {"$ref": f"#/components/schemas/{name}"}}}]}


def op(method, summary, perm, req=None, resp="Envelope", params=None, sse=False):
    if perm == "public":
        sec = []
    elif perm == "authenticated":
        sec = [{"sessionCookie": []}, {"bearerToken": []}]
    else:
        sec = [{"sessionCookie": []}, {"bearerToken": []}]
    o = {"summary": summary, "x-permission": perm, "security": sec}
    all_params = list(params or [])
    if sse:
        all_params.append({"name": "Last-Event-ID", "in": "header", "required": False, "description": "Durable cursor: replay everything after this event id", "schema": {"type": "string"}})
    if all_params:
        o["parameters"] = all_params
    if req:
        o["requestBody"] = {"required": True, "content": {"application/json": {"schema": req}}}
    content_type = "text/event-stream" if sse else "application/json"
    success = "200" if method in ("get", "put", "patch") else "201"
    if method == "delete":
        o["responses"] = {"204": {"description": "Deleted (no content)"},
                          "400": REF("BadRequest"), "401": REF("Unauthorized"), "403": REF("Forbidden"),
                          "404": REF("NotFound"), "409": REF("Conflict"), "422": REF("Unprocessable"), "429": REF("RateLimited")}
        return {method: o}
    o["responses"] = {
        success: {"description": "OK", "content": {content_type: {"schema": resolve_resp(resp)}}},
        "400": REF("BadRequest"), "401": REF("Unauthorized"), "403": REF("Forbidden"),
        "404": REF("NotFound"), "409": REF("Conflict"), "422": REF("Unprocessable"), "429": REF("RateLimited")}
    return {method: o}


cursor = P("cursor", type="string")
limit = P("limit", schema={"type": "integer", "default": 50, "maximum": 200})


paths = {}

# ---- auth ----
paths["/auth/login"] = op("post", "Start session", "public", body({"email": {"type": "string", "format": "email"}, "password": {"type": "string"}, "mfa_code": {"type": "string", "description": "Required only when the account has MFA enrolled"}}, ["email", "password"]), resp="AuthResult")
paths["/auth/register"] = op("post", "Register workspace", "public", body({"email": {"type": "string"}, "password": {"type": "string"}, "workspace_name": {"type": "string"}}), resp="AuthResult")
paths["/auth/logout"] = op("post", "End session", "authenticated")
paths["/auth/oauth/{provider}"] = {"get": op("get", "Start OAuth login", "public", None, resp="OAuthStart", params=[path_param("provider")])["get"], "post": op("post", "Complete OAuth login (code exchange)", "public", body({"code": {"type": "string"}, "state": {"type": "string"}}), resp="AuthResult", params=[path_param("provider")])["post"]}
paths["/auth/mfa/verify"] = op("post", "Verify MFA", "authenticated", body({"code": {"type": "string"}}), resp="AuthResult")
paths["/auth/password/reset-request"] = op("post", "Request password reset", "public", body({"email": {"type": "string", "format": "email"}}))
paths["/auth/password/reset"] = op("post", "Reset password", "public", body({"token": {"type": "string"}, "password": {"type": "string"}}))
paths["/auth/invitations/accept"] = op("post", "Accept invitation", "public", body({"token": {"type": "string"}, "password": {"type": "string"}}), resp="AuthResult")

# ---- me ----
paths["/me"] = {"get": op("get", "Current user", "authenticated", resp="User")["get"],
                "patch": op("patch", "Update profile", "authenticated", body({"name": {"type": "string"}, "avatar": {"type": "string"}}, []), resp="User")["patch"]}
paths["/me/permissions"] = op("get", "Effective permissions", "authenticated", resp="PermissionSet")
paths["/me/sessions"] = op("get", "List sessions", "authenticated", resp="SessionList")
paths["/me/sessions/{id}/revoke"] = op("post", "Revoke session", "authenticated", None, params=[path_param("id")])
paths["/me/mfa"] = op("post", "Enroll MFA", "authenticated", body({"type": {"const": "totp"}}), resp="MfaEnrollment")
paths["/me/tokens"] = {"get": op("get", "List personal API keys", "authenticated", resp="ApiTokenList")["get"], "post": op("post", "Create personal API key (value shown once)", "authenticated", body({"name": {"type": "string"}, "expires_at": {"type": "string", "format": "date-time"}, "scopes": {"type": "array", "items": {"type": "string"}}}), resp="ApiToken")["post"]}
paths["/me/tokens/{id}"] = {"get": op("get", "Token detail", "authenticated", None, resp="ApiToken", params=[path_param("id")])["get"],
                           "delete": op("delete", "Revoke token", "authenticated", None, params=[path_param("id")])["delete"]}
paths["/me/notifications"] = {"get": op("get", "Notifications", "authenticated", resp="NotificationList")["get"],
                              "patch": op("patch", "Update notification prefs", "authenticated", body({"channel": {"type": "string"}, "events": {"type": "array", "items": {"type": "string"}}}), resp="Notification")["patch"]}

# ---- members/roles ----
paths["/members"] = op("get", "List members", "member:read", resp="UserList")
paths["/invitations"] = {"get": op("get", "List invitations", "member:read", resp="InvitationList")["get"],
                        "post": op("post", "Invite member", "member:invite", body({"email": {"type": "string", "format": "email"}, "role": {"type": "string"}}), resp="Invitation")["post"]}
paths["/members/{id}"] = {"patch": op("patch", "Change role / status", "member:manage", body({"role": {"type": "string"}, "status": {"type": "string"}}, []), params=[path_param("id")], resp="User")["patch"],
                          "delete": op("delete", "Deactivate member", "member:manage", None, params=[path_param("id")])["delete"]}
paths["/roles"] = {"get": op("get", "List roles", "member:read", resp="RoleList")["get"],
                  "post": op("post", "Create role", "role:manage", body({"name": {"type": "string"}, "permissions": {"type": "array", "items": {"type": "string"}}}), resp="Role")["post"]}
paths["/roles/{id}"] = {"patch": op("patch", "Update role", "role:manage", body({"permissions": {"type": "array", "items": {"type": "string"}}}, []), params=[path_param("id")], resp="Role")["patch"],
                       "delete": op("delete", "Delete role", "role:manage", None, params=[path_param("id")])["delete"]}

# ---- projects ----
paths["/projects"] = {"get": op("get", "List projects", "project:read", resp="ProjectList")["get"],
                     "post": op("post", "Create project", "project:create", body({"name": {"type": "string"}}), resp="Project")["post"]}
paths["/projects/{id}"] = {"get": op("get", "Project detail", "project:read", None, params=[path_param("id")], resp="Project")["get"],
                          "patch": op("patch", "Update project", "project:edit", body({"name": {"type": "string"}, "archived": {"type": "boolean"}}, []), params=[path_param("id")], resp="Project")["patch"],
                          "delete": op("delete", "Archive project", "project:delete", None, params=[path_param("id")])["delete"]}

# ---- agents ----
paths["/agents"] = {"get": op("get", "List agents", "agent:read", resp="AgentList", params=[cursor, limit, P("status", schema={"enum": ["draft", "published", "paused", "archived", "failed"]}), P("project_id")])["get"],
                    "post": op("post", "Create agent draft", "agent:create", {"$ref": "#/components/schemas/AgentConfig"}, resp="Agent")["post"]}
paths["/agents/templates"] = op("get", "List templates", "agent:read", resp="AgentTemplateList")
paths["/agents/{id}"] = {"get": op("get", "Agent detail", "agent:read", None, params=[path_param("id")], resp="Agent")["get"],
                        "patch": op("patch", "Update draft / status", "agent:edit", body({"draft": {"$ref": "#/components/schemas/AgentConfig"}, "action": {"enum": ["pause", "resume", "archive", "restore"]}}, []), params=[path_param("id")], resp="Agent")["patch"],
                        "delete": op("delete", "Soft-delete agent", "agent:delete", None, params=[path_param("id")])["delete"]}
paths["/agents/{id}/draft"] = {"get": op("get", "Get draft", "agent:read", None, params=[path_param("id")], resp="Agent")["get"],
                              "put": op("put", "Save draft (If-Match concurrency)", "agent:edit", {"$ref": "#/components/schemas/AgentConfig"}, params=[path_param("id")], resp="Agent")["put"]}
paths["/agents/{id}/validate"] = op("post", "Validate config", "agent:edit", None, resp="ValidationReport", params=[path_param("id")])
paths["/agents/{id}/publish"] = op("post", "Publish immutable version", "agent:publish", body({"notes": {"type": "string"}}, []), params=[path_param("id")], resp="Agent")
paths["/agents/{id}/versions"] = op("get", "Version history", "agent:read", None, params=[path_param("id")], resp="AgentVersionList")
paths["/agents/{id}/versions/{v}/export"] = op("get", "Export version bundle", "agent:read", None, resp="ExportBundle", params=[path_param("id"), P("v", "path", required=True, schema={"type": "integer"})])
paths["/agents/import"] = op("post", "Import agent bundle", "agent:create", body({"bundle": {"type": "object"}}), resp="Agent")
paths["/agents/{id}/clone"] = op("post", "Clone agent", "agent:create", body({"key_suffix": {"type": "string"}}, []), params=[path_param("id")], resp="Agent")
paths["/agents/{id}/test"] = op("post", "Sandbox test run", "agent:execute", body({"input": {"type": "object"}}, []), params=[path_param("id")], resp="Run")

# ---- workflows ----
paths["/workflows"] = {"get": op("get", "List workflows", "workflow:read", resp="WorkflowList", params=[cursor, limit, P("status")])["get"],
                      "post": op("post", "Create workflow", "workflow:create", {"$ref": "#/components/schemas/WorkflowDef"}, resp="Workflow")["post"]}
paths["/workflows/{id}"] = {"get": op("get", "Workflow detail", "workflow:read", None, params=[path_param("id")], resp="Workflow")["get"],
                           "patch": op("patch", "Update draft / status", "workflow:edit", body({"draft": {"$ref": "#/components/schemas/WorkflowDef"}, "action": {"enum": ["pause", "resume", "archive"]}}, []), params=[path_param("id")], resp="Workflow")["patch"],
                           "delete": op("delete", "Delete workflow", "workflow:delete", None, params=[path_param("id")])["delete"]}
paths["/workflows/{id}/draft"] = {"get": op("get", "Get draft", "workflow:read", None, params=[path_param("id")], resp="Workflow")["get"],
                                "put": op("put", "Save draft (If-Match)", "workflow:edit", {"$ref": "#/components/schemas/WorkflowDef"}, params=[path_param("id")], resp="Workflow")["put"]}
paths["/workflows/{id}/validate"] = op("post", "Validate graph", "workflow:edit", None, resp="ValidationReport", params=[path_param("id")])
paths["/workflows/{id}/publish"] = op("post", "Publish version", "workflow:publish", body({"notes": {"type": "string"}}, []), params=[path_param("id")], resp="Workflow")
paths["/workflows/{id}/versions"] = op("get", "Version history", "workflow:read", None, params=[path_param("id")], resp="WorkflowVersionList")
paths["/workflows/{id}/versions/{v}"] = op("get", "Version detail (graph)", "workflow:read", None, params=[path_param("id"), P("v", "path", required=True, schema={"type": "integer"})], resp="WorkflowVersion")
paths["/workflows/{id}/clone"] = op("post", "Duplicate workflow", "workflow:create", None, params=[path_param("id")], resp="Workflow")
paths["/workflows/import"] = op("post", "Import workflow bundle", "workflow:create", body({"bundle": {"type": "object"}}), resp="Workflow")
paths["/workflows/{id}/test"] = op("post", "Test run (pause-at-node allowed)", "workflow:execute", body({"input": {"type": "object"}, "pause_at_node": {"type": "string"}}, ["input"]), params=[path_param("id")], resp="Run")

# ---- runs ----
paths["/runs"] = {"get": op("get", "List runs", "run:read", resp="RunList", params=[cursor, limit, P("status"), P("workflow_id"), P("agent_id"), P("trigger"), P("since")])["get"],
                 "post": op("post", "Start run (Idempotency-Key header)", "run:create", {"$ref": "#/components/schemas/StartRunRequest"}, resp="Run", params=[{"name": "Idempotency-Key", "in": "header", "required": True, "schema": {"type": "string"}, "description": "Duplicate submissions with the same key return the original run"}])["post"]}
paths["/runs/{id}"] = op("get", "Run detail", "run:read", resp="Run", params=[path_param("id")])
paths["/runs/{id}/events"] = op("get", "SSE event stream (Last-Event-ID replay)", "run:read", None, params=[path_param("id")], sse=True)
paths["/runs/{id}/cancel"] = op("post", "Cancel run", "run:cancel", None, resp="Run", params=[path_param("id")])
paths["/runs/{id}/replay"] = op("post", "Replay as new run", "run:create", None, resp="Run", params=[path_param("id")])
paths["/runs/{id}/nodes/{nodeId}/retry"] = op("post", "Retry failed node as new run", "run:create", None, resp="Run", params=[path_param("id"), P("nodeId", "path", required=True)])
paths["/runs/{id}/artifacts/{key}"] = op("get", "Get artifact (presigned)", "run:read", None, resp="Artifact", params=[path_param("id"), P("key", "path", required=True)])

# ---- tasks/approvals ----
paths["/tasks"] = {"get": op("get", "List tasks", "task:read", resp="TaskList", params=[cursor, limit, P("state"), P("assignee")])["get"],
                  "post": op("post", "Create task", "task:create", body({"title": {"type": "string"}, "run_id": {"type": "string"}}, ["title"]), resp="Task")["post"]}
paths["/tasks/{id}"] = {"get": op("get", "Task detail", "task:read", None, params=[path_param("id")], resp="Task")["get"],
                        "patch": op("patch", "Update task", "task:edit", body({"state": {"type": "string"}, "assignee": {"type": "string"}}, []), params=[path_param("id")], resp="Task")["patch"]}
paths["/approvals"] = op("get", "List approvals", "approval:read", resp="ApprovalList", params=[cursor, limit, P("status")])
paths["/approvals/{id}"] = op("get", "Approval detail", "approval:read", resp="Approval", params=[path_param("id")])
paths["/approvals/{id}/decide"] = op("post", "Decide approval", "approval:decide", body({"decision": {"enum": ["approve", "reject"]}, "comment": {"type": "string"}}), resp="Approval", params=[path_param("id")])

# ---- inbox/activity/search/events ----
paths["/inbox"] = op("get", "Inbox (approvals, mentions, notifications)", "authenticated", resp="InboxItemList", params=[cursor, limit])
paths["/activity"] = op("get", "Activity feed", "activity:read", resp="ActivityEventList", params=[cursor, limit, P("type"), P("actor")])
paths["/search"] = op("get", "Global search", "search:read", resp="SearchResultList", params=[P("q", required=True), P("kinds")])
paths["/events"] = op("get", "SSE workspace events (inbox/notifications)", "authenticated", sse=True)

# ---- models ----
paths["/providers"] = {"get": op("get", "List providers", "model:read", resp="ProviderList")["get"],
                       "post": op("post", "Add provider config", "model:configure", body({"kind": {"type": "string"}, "name": {"type": "string"}, "litellm_config_ref": {"type": "string"}}), resp="Provider")["post"]}
paths["/providers/{id}"] = {"get": op("get", "Provider detail", "model:read", None, resp="Provider", params=[path_param("id")])["get"],
                            "delete": op("delete", "Remove provider", "model:configure", None, params=[path_param("id")])["delete"]}
paths["/providers/{id}/health"] = op("post", "Health probe", "model:configure", None, resp="HealthStatus", params=[path_param("id")])
paths["/models"] = {"get": op("get", "Model catalog (capability matrix)", "model:read", resp="ModelEntryList")["get"],
                    "post": op("post", "Register model", "model:configure", {"$ref": "#/components/schemas/ModelEntry"}, resp="ModelEntry")["post"]}
paths["/models/{id}"] = {"patch": op("patch", "Update model entry", "model:configure", body({"status": {"type": "string"}, "pricing": {"type": "object"}}, []), params=[path_param("id")], resp="ModelEntry")["patch"],
                        "delete": op("delete", "Remove model", "model:configure", None, params=[path_param("id")])["delete"]}
paths["/routing"] = {"get": op("get", "List routing rules", "model:read", resp="RoutingRuleList")["get"],
                    "post": op("post", "Create routing rule", "model:configure", body({"priority": {"type": "integer"}, "match": {"type": "object"}, "target_alias": {"type": "string"}, "fallbacks": {"type": "array", "items": {"type": "string"}}}), resp="RoutingRule")["post"]}
paths["/routing/preview"] = op("post", "Resolve rules for hypothetical request", "model:read", body({"agent_key": {"type": "string"}, "tag": {"type": "string"}}, []), resp="RoutingPreview")

# ---- tools ----
paths["/tools"] = {"get": op("get", "List tools", "tool:read", resp="ToolDefList", params=[cursor, limit, P("kind"), P("risk_class")])["get"],
                   "post": op("post", "Register tool", "tool:install", {"$ref": "#/components/schemas/ToolDef"}, resp="ToolDef")["post"]}
paths["/tools/{id}"] = {"get": op("get", "Tool detail", "tool:read", None, params=[path_param("id")], resp="ToolDef")["get"],
                       "patch": op("patch", "Update draft / status", "tool:edit", body({"draft": {"$ref": "#/components/schemas/ToolDef"}, "action": {"enum": ["disable", "enable"]}}, []), params=[path_param("id")], resp="ToolDef")["patch"],
                       "delete": op("delete", "Delete tool", "tool:install", None, params=[path_param("id")])["delete"]}
paths["/tools/{id}/publish"] = op("post", "Publish tool version", "tool:install", None, resp="ToolDef", params=[path_param("id")])
paths["/tools/{id}/test"] = op("post", "Test tool in sandbox", "tool:execute", body({"input": {"type": "object"}}, ["input"]), resp="ToolTestResult", params=[path_param("id")])
paths["/tools/{id}/usage"] = op("get", "Tool usage stats", "tool:read", None, resp="ToolUsageStats", params=[path_param("id")])
paths["/integrations"] = {"get": op("get", "List integrations", "tool:read", resp="IntegrationList")["get"],
                          "post": op("post", "Connect integration", "tool:install", body({"kind": {"type": "string"}, "config": {"type": "object"}, "secret_refs": {"type": "array", "items": {"type": "string"}}}), resp="Integration")["post"]}
paths["/mcp/servers"] = {"get": op("get", "List MCP servers", "tool:read", resp="McpServerList")["get"],
                        "post": op("post", "Register MCP server", "tool:install", body({"name": {"type": "string"}, "transport": {"enum": ["stdio", "streamable_http"]}, "endpoint": {"type": "string"}, "auth": {"type": "object"}}), resp="McpServer")["post"]}
paths["/mcp/servers/{id}/discover"] = op("post", "Discover tools from server", "tool:install", None, resp="ToolDefList", params=[path_param("id")])
paths["/mcp/servers/{id}"] = {"delete": op("delete", "Remove MCP server", "tool:install", None, params=[path_param("id")])["delete"]}
paths["/skills"] = {"get": op("get", "List skills", "skill:read", resp="SkillList")["get"],
                    "post": op("post", "Create skill", "skill:create", body({"key": {"type": "string"}, "instructions": {"type": "string"}, "tools": {"type": "array", "items": {"type": "string"}}}), resp="Skill")["post"]}
paths["/skills/{id}/publish"] = op("post", "Publish skill version", "skill:publish", None, resp="Skill", params=[path_param("id")])

# ---- knowledge ----
paths["/knowledge/sources"] = {"get": op("get", "List sources", "knowledge:read", resp="KnowledgeSourceList")["get"],
                              "post": op("post", "Connect source", "knowledge:write", body({"kind": {"type": "string"}, "config": {"type": "object"}}), resp="KnowledgeSource")["post"]}
paths["/collections"] = {"get": op("get", "List collections", "knowledge:read", resp="CollectionList")["get"],
                         "post": op("post", "Create collection", "knowledge:manage", body({"name": {"type": "string"}, "acl": {"type": "object"}, "settings": {"type": "object"}}), resp="Collection")["post"]}
paths["/collections/{id}"] = {"get": op("get", "Collection detail", "knowledge:read", None, params=[path_param("id")], resp="Collection")["get"],
                             "patch": op("patch", "Update collection", "knowledge:manage", body({"name": {"type": "string"}, "acl": {"type": "object"}}, []), params=[path_param("id")], resp="Collection")["patch"],
                             "delete": op("delete", "Delete collection (cascades)", "knowledge:manage", None, params=[path_param("id")])["delete"]}
paths["/collections/{id}/documents"] = {"get": op("get", "List documents", "knowledge:read", None, resp="DocumentList", params=[path_param("id")])["get"],
                                        "post": op("post", "Create presigned upload", "knowledge:write", body({"filename": {"type": "string"}, "size_bytes": {"type": "integer"}, "content_type": {"type": "string"}}), resp="PresignResult", params=[path_param("id")])["post"]}
paths["/collections/{id}/retrieve"] = op("post", "Permission-aware retrieval", "knowledge:read", body({"query": {"type": "string"}, "top_k": {"type": "integer"}, "filter": {"type": "object"}}, ["query"]), resp="RetrieveResult", params=[path_param("id")])
paths["/collections/{id}/reindex"] = op("post", "Rebuild index version", "knowledge:manage", None, resp="Collection", params=[path_param("id")])
paths["/documents/{id}"] = {"get": op("get", "Document detail", "knowledge:read", None, resp="Document", params=[path_param("id")])["get"],
                            "delete": op("delete", "Delete document", "knowledge:write", None, params=[path_param("id")])["delete"]}

# ---- memory ----
paths["/memory"] = op("get", "List memory records", "memory:read", resp="MemoryRecordList", params=[cursor, limit, P("scope"), P("owner")])
paths["/memory/{id}"] = {"get": op("get", "Memory record", "memory:read", None, params=[path_param("id")], resp="MemoryRecord")["get"],
                        "patch": op("patch", "Edit / approve suggested memory", "memory:write", body({"content": {"type": "string"}, "status": {"enum": ["approved", "rejected"]}}, []), params=[path_param("id")], resp="MemoryRecord")["patch"],
                        "delete": op("delete", "Delete memory", "memory:write", None, params=[path_param("id")])["delete"]}

# ---- schedules/triggers/webhooks ----
paths["/schedules"] = {"get": op("get", "List schedules", "schedule:read", resp="ScheduleList")["get"],
                      "post": op("post", "Create schedule", "schedule:manage", body({"workflow_id": {"type": "string"}, "workflow_version": {"type": "integer"}, "cron": {"type": "string"}, "input": {"type": "object"}}), resp="Schedule")["post"]}
paths["/schedules/{id}"] = {"patch": op("patch", "Pause/resume/update", "schedule:manage", body({"action": {"enum": ["pause", "resume"]}}, []), params=[path_param("id")], resp="Schedule")["patch"],
                           "delete": op("delete", "Delete schedule", "schedule:manage", None, params=[path_param("id")])["delete"]}
paths["/schedules/{id}/run"] = op("post", "Trigger scheduled run now", "schedule:manage", None, resp="Run", params=[path_param("id")])
paths["/triggers"] = {"get": op("get", "List triggers", "trigger:read", resp="TriggerList")["get"],
                     "post": op("post", "Create trigger", "trigger:manage", body({"event_type": {"type": "string"}, "filter": {"type": "object"}, "workflow_id": {"type": "string"}, "workflow_version": {"type": "integer"}}), resp="Trigger")["post"]}
paths["/triggers/{id}"] = {"delete": op("delete", "Delete trigger", "trigger:manage", None, params=[path_param("id")])["delete"]}
paths["/webhooks"] = {"get": op("get", "List webhooks", "webhook:read", resp="WebhookList")["get"],
                     "post": op("post", "Create webhook endpoint", "webhook:manage", body({"events": {"type": "array", "items": {"type": "string"}}}), resp="Webhook")["post"]}
paths["/webhooks/{id}"] = {"delete": op("delete", "Delete webhook", "webhook:manage", None, params=[path_param("id")])["delete"]}
paths["/webhooks/{id}/rotate-secret"] = op("post", "Rotate signing secret", "webhook:manage", None, resp="Webhook", params=[path_param("id")])
paths["/webhooks/{id}/test"] = op("post", "Send test event", "webhook:manage", body({"event": {"type": "string"}}, []), resp="WebhookTestResult", params=[path_param("id")])

# ---- evals ----
paths["/evaluations/datasets"] = {"get": op("get", "List datasets", "eval:read", resp="EvalDatasetList")["get"],
                                  "post": op("post", "Create dataset", "eval:run", body({"name": {"type": "string"}, "records_uri": {"type": "string"}}), resp="EvalDataset")["post"]}
paths["/evaluations/datasets/{id}"] = {"get": op("get", "Dataset detail", "eval:read", None, params=[path_param("id")], resp="EvalDataset")["get"],
                                      "delete": op("delete", "Delete dataset", "eval:run", None, params=[path_param("id")])["delete"]}
paths["/evaluations/experiments"] = {"get": op("get", "List experiments", "eval:read", resp="EvalRunList")["get"],
                                   "post": op("post", "Launch experiment", "eval:run", body({"dataset_id": {"type": "string"}, "subject_a": {"$ref": "#/components/schemas/EvalSubject"}, "subject_b": {"$ref": "#/components/schemas/EvalSubject"}, "repetitions": {"type": "integer", "default": 3}}), resp="EvalRun")["post"]}
paths["/evaluations/runs"] = op("get", "List eval runs", "eval:read", resp="EvalRunList", params=[cursor, limit, P("status")])
paths["/evaluations/runs/{id}"] = op("get", "Eval run results", "eval:read", None, params=[path_param("id")], resp="EvalRun")

# ---- analytics/budgets ----
for slug, summ in [("overview", "Ops dashboard"), ("costs", "Cost breakdown"), ("latency", "Latency analysis"), ("reliability", "Reliability metrics"), ("models", "Model usage")]:
    paths[f"/analytics/{slug}"] = op("get", summ, "analytics:read", resp="AnalyticsSeries", params=[P("since"), P("until"), P("workflow_id")])
paths["/budgets/policies"] = {"get": op("get", "List budget policies", "budget:read", resp="BudgetPolicyList")["get"],
                              "put": op("put", "Upsert budget policy", "budget:manage", {"$ref": "#/components/schemas/BudgetPolicy"}, resp="BudgetPolicy")["put"]}
paths["/budgets/reservations/{runId}"] = op("get", "Reservation status for run", "budget:read", None, resp="BudgetReservation", params=[P("runId", "path", required=True)])

# ---- audit/admin ----
paths["/audit"] = op("get", "Audit log (immutable)", "audit:read", resp="AuditEventList", params=[cursor, limit, P("actor"), P("action"), P("resource_type"), P("since"), P("until")])
paths["/audit/export"] = op("get", "Export audit log", "audit:export", None, resp="AuditExport", params=[P("since"), P("until")])
paths["/admin/users"] = op("get", "Admin: list users", "admin:users", resp="UserList", params=[cursor, limit])
paths["/admin/users/{id}"] = {"patch": op("patch", "Admin: suspend / force logout", "admin:users", body({"status": {"enum": ["active", "suspended"]}}, []), params=[path_param("id")], resp="User")["patch"]}
paths["/admin/policies"] = {"get": op("get", "List policies", "admin:policies", resp="PolicyList")["get"],
                            "put": op("put", "Upsert policy", "admin:policies", body({"kind": {"type": "string"}, "rules": {"type": "object"}, "version": {"type": "integer"}}), resp="Policy")["put"]}
paths["/admin/health"] = op("get", "Component health", "admin:system", resp="HealthStatus")

# ---- workspace/secrets ----
paths["/workspace"] = {"get": op("get", "Workspace settings", "workspace:read", resp="Workspace")["get"],
                      "patch": op("patch", "Update workspace", "workspace:manage", body({"name": {"type": "string"}, "settings": {"type": "object"}}, []), resp="Workspace")["patch"]}
paths["/secrets"] = {"get": op("get", "List secret metadata (never values)", "secret:read", resp="SecretMetaList")["get"],
                    "post": op("post", "Create secret", "secret:write", body({"name": {"type": "string"}, "value": {"type": "string"}, "kms_key_ref": {"type": "string"}}), resp="SecretMeta")["post"]}
paths["/secrets/{id}"] = {"delete": op("delete", "Delete secret", "secret:write", None, params=[path_param("id")])["delete"]}
paths["/secrets/{id}/rotate"] = op("post", "Rotate secret", "secret:rotate", body({"value": {"type": "string"}}, ["value"]), resp="SecretMeta", params=[path_param("id")])


schemas = {
    "Error": {"type": "object", "required": ["error"], "properties": {"error": {"type": "object", "required": ["code", "message"], "properties": {"code": {"type": "string", "examples": ["VALIDATION_FAILED", "BUDGET_EXCEEDED", "MODEL_CAPABILITY_MISMATCH", "APPROVAL_STALE"]}, "message": {"type": "string"}, "details": {"type": "object", "additionalProperties": True}, "correlation_id": {"type": "string"}}}}},
    "Envelope": {"type": "object", "required": ["data"], "properties": {"data": {}, "meta": {"type": "object", "properties": {"next_cursor": {"type": ["string", "null"]}}}}},
    "RunStatus": {"type": "string", "enum": ["queued", "running", "waiting_approval", "waiting_review", "retrying", "completed", "failed", "cancelled", "timed_out"]},
    "StartRunRequest": {"type": "object", "required": ["workflow_id", "workflow_version", "input"], "properties": {"workflow_id": {"type": "string"}, "workflow_version": {"type": "integer"}, "input": {"type": "object", "additionalProperties": True}}},
    "Run": {"type": "object", "required": ["id", "workflow_id", "status"], "properties": {"id": {"type": "string"}, "workspace_id": {"type": "string"}, "workflow_id": {"type": "string"}, "workflow_version": {"type": "integer"}, "status": {"$ref": "#/components/schemas/RunStatus"}, "trigger": {"type": "object", "properties": {"type": {"enum": ["manual", "api", "schedule", "webhook", "replay"]}, "user_id": {"type": "string"}}}, "cost": {"type": "object", "properties": {"estimated_usd": {"type": "number"}, "reported_usd": {"type": ["number", "null"]}, "reconciled_usd": {"type": ["number", "null"]}}}, "tokens": {"type": "object", "properties": {"input": {"type": "integer"}, "output": {"type": "integer"}}}, "started_at": {"type": "string", "format": "date-time"}, "ended_at": {"type": ["string", "null"], "format": "date-time"}, "retry_of": {"type": ["string", "null"]}}},
    "Approval": {"type": "object", "required": ["id", "run_id", "status"], "properties": {"id": {"type": "string"}, "run_id": {"type": "string"}, "node_id": {"type": "string"}, "action": {"type": "string"}, "tool_version": {"type": "integer"}, "args_hash": {"type": "string"}, "risk_class": {"enum": ["low", "medium", "high", "critical"]}, "status": {"enum": ["pending", "approved", "rejected", "expired", "stale"]}, "expires_at": {"type": "string", "format": "date-time"}, "delivery": {"enum": ["decision_recorded", "delivered", "workflow_resumed"]}}},
    "AgentConfig": {"type": "object", "required": ["key", "name", "instructions", "model"], "properties": {"key": {"type": "string", "pattern": "^[a-z0-9-]+$"}, "name": {"type": "string"}, "description": {"type": "string"}, "instructions": {"type": "string"}, "model": {"type": "object", "properties": {"provider": {"type": "string"}, "model": {"type": "string"}, "parameters": {"type": "object", "additionalProperties": True}, "fallbacks": {"type": "array", "items": {"type": "string"}}}}, "tools": {"type": "array", "items": {"type": "object"}}, "limits": {"type": "object", "properties": {"max_duration_s": {"type": "integer"}, "max_tool_calls": {"type": "integer"}, "max_tokens": {"type": "integer"}, "max_cost_usd": {"type": "number"}, "max_retries": {"type": "integer"}, "concurrency": {"type": "integer"}}}}},
    "WorkflowDef": {"type": "object", "required": ["key", "nodes", "edges", "budget"], "properties": {"key": {"type": "string", "pattern": "^[a-z0-9-]+$"}, "name": {"type": "string"}, "variables": {"type": "object", "additionalProperties": {"type": "object"}}, "budget": {"type": "object"}, "nodes": {"type": "array", "items": {"type": "object", "required": ["id", "type", "config"]}}, "edges": {"type": "array", "items": {"type": "object", "required": ["from", "to"]}}, "error_policies": {"type": "object"}}},
    "ToolDef": {"type": "object", "required": ["key", "kind", "input_schema", "output_schema", "risk_class", "environment"], "properties": {"key": {"type": "string"}, "name": {"type": "string"}, "kind": {"enum": ["builtin", "integration", "mcp", "custom"]}, "input_schema": {"type": "object"}, "output_schema": {"type": "object"}, "auth": {"type": "object"}, "scopes": {"type": "array", "items": {"type": "string"}}, "timeout_s": {"type": "integer"}, "retry": {"type": "object"}, "environment": {"enum": ["api", "sandbox", "mcp"]}, "risk_class": {"enum": ["low", "medium", "high", "critical"]}, "idempotent": {"type": "boolean", "description": "Derived from tool contract, not user-asserted"}, "approval_policy": {"enum": ["never", "on_high_risk", "always"]}}},
    "ModelEntry": {"type": "object", "required": ["provider_id", "model_id", "capabilities", "status"], "properties": {"provider_id": {"type": "string"}, "model_id": {"type": "string"}, "capabilities": {"type": "object", "properties": {"chat": {"type": "boolean"}, "streaming": {"type": "boolean"}, "tools": {"type": "boolean"}, "structured_output": {"type": "boolean"}, "vision": {"type": "boolean"}, "embeddings": {"type": "boolean"}, "prompt_caching": {"type": "boolean"}, "usage_reporting": {"enum": ["none", "tokens", "detailed"]}}, "context_window": {"type": "integer"}, "max_output_tokens": {"type": "integer"}, "pricing": {"type": "object", "properties": {"input_per_mtok_usd": {"type": "number"}, "output_per_mtok_usd": {"type": "number"}}}, "status": {"enum": ["active", "deprecated", "hidden"]}}}},
    "EvalSubject": {"type": "object", "properties": {"kind": {"enum": ["agent_version", "model_alias", "prompt"]}, "ref": {"type": "string"}}},
    "BudgetPolicy": {"type": "object", "required": ["scope", "limits"], "properties": {"scope": {"enum": ["workspace", "project", "agent", "run"]}, "limits": {"type": "object", "properties": {"max_tokens": {"type": "integer"}, "max_cost_usd": {"type": "number"}, "max_duration_s": {"type": "integer"}, "max_parallel_agents": {"type": "integer"}, "max_tool_calls": {"type": "integer"}, "max_recursion_depth": {"type": "integer"}, "max_retries": {"type": "integer"}}}, "alerts": {"type": "array", "items": {"type": "integer"}}}},
    "User": {"type": "object", "required": ["id", "email", "name", "status"], "properties": {"id": {"type": "string"}, "email": {"type": "string", "format": "email"}, "name": {"type": "string"}, "role": {"type": "string"}, "status": {"enum": ["active", "suspended", "invited"]}, "mfa_enabled": {"type": "boolean"}, "created_at": {"type": "string", "format": "date-time"}, "last_login_at": {"type": ["string", "null"], "format": "date-time"}}},
    "Project": {"type": "object", "required": ["id", "name", "status"], "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "description": {"type": "string"}, "status": {"enum": ["active", "archived"]}, "created_at": {"type": "string", "format": "date-time"}, "archived_at": {"type": ["string", "null"], "format": "date-time"}}},
    "Agent": {"type": "object", "required": ["id", "key", "name", "status"], "properties": {"id": {"type": "string"}, "key": {"type": "string"}, "name": {"type": "string"}, "status": {"enum": ["draft", "published", "paused", "archived"]}, "current_version": {"type": ["integer", "null"]}, "draft": {"$ref": "#/components/schemas/AgentConfig"}, "created_by": {"type": "string"}, "created_at": {"type": "string", "format": "date-time"}, "updated_at": {"type": "string", "format": "date-time"}}},
    "AgentVersion": {"type": "object", "required": ["version", "status", "config"], "properties": {"version": {"type": "integer"}, "status": {"enum": ["published", "retired"]}, "config": {"$ref": "#/components/schemas/AgentConfig"}, "published_at": {"type": "string", "format": "date-time"}, "published_by": {"type": "string"}, "notes": {"type": "string"}}},
    "Workflow": {"type": "object", "required": ["id", "key", "name", "status"], "properties": {"id": {"type": "string"}, "key": {"type": "string"}, "name": {"type": "string"}, "status": {"enum": ["draft", "published", "paused", "archived"]}, "current_version": {"type": ["integer", "null"]}, "draft": {"$ref": "#/components/schemas/WorkflowDef"}, "created_by": {"type": "string"}, "created_at": {"type": "string", "format": "date-time"}, "updated_at": {"type": "string", "format": "date-time"}}},
    "WorkflowVersion": {"type": "object", "required": ["version", "status", "definition"], "properties": {"version": {"type": "integer"}, "status": {"enum": ["published", "retired"]}, "definition": {"$ref": "#/components/schemas/WorkflowDef"}, "published_at": {"type": "string", "format": "date-time"}, "published_by": {"type": "string"}, "notes": {"type": "string"}}},
    "Task": {"type": "object", "required": ["id", "title", "state"], "properties": {"id": {"type": "string"}, "title": {"type": "string"}, "state": {"enum": ["open", "in_progress", "done", "cancelled"]}, "assignee": {"type": ["string", "null"]}, "run_id": {"type": ["string", "null"]}, "created_at": {"type": "string", "format": "date-time"}, "updated_at": {"type": "string", "format": "date-time"}}},
    "EvalDataset": {"type": "object", "required": ["id", "name", "records_uri"], "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "records_uri": {"type": "string"}, "record_count": {"type": "integer"}, "created_at": {"type": "string", "format": "date-time"}}},
    "EvalRun": {"type": "object", "required": ["id", "status"], "properties": {"id": {"type": "string"}, "experiment_id": {"type": ["string", "null"]}, "status": {"enum": ["running", "completed", "failed"]}, "subjects": {"type": "array", "items": {"$ref": "#/components/schemas/EvalSubject"}}, "summary": {"type": "object", "additionalProperties": True}, "report_uri": {"type": "string"}, "started_at": {"type": "string", "format": "date-time"}, "ended_at": {"type": ["string", "null"], "format": "date-time"}}},
    "AuditEvent": {"type": "object", "required": ["id", "actor", "action", "timestamp"], "properties": {"id": {"type": "string"}, "actor": {"type": "string"}, "action": {"type": "string"}, "resource_type": {"type": "string"}, "resource_id": {"type": "string"}, "correlation_id": {"type": "string"}, "timestamp": {"type": "string", "format": "date-time"}}},
    "Policy": {"type": "object", "required": ["kind", "rules", "version"], "properties": {"kind": {"type": "string"}, "rules": {"type": "object"}, "version": {"type": "integer"}, "updated_at": {"type": "string", "format": "date-time"}}},
    "Collection": {"type": "object", "required": ["id", "name"], "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "acl": {"type": "object"}, "settings": {"type": "object"}, "indexed_version": {"type": "integer"}, "document_count": {"type": "integer"}, "created_at": {"type": "string", "format": "date-time"}}},
    "MemoryRecord": {"type": "object", "required": ["id", "scope", "content", "status"], "properties": {"id": {"type": "string"}, "scope": {"type": "string"}, "owner": {"type": "string"}, "content": {"type": "string"}, "status": {"enum": ["suggested", "approved", "rejected"]}, "created_at": {"type": "string", "format": "date-time"}}},
    "AuthResult": {"type": "object", "required": ["user", "session_id"], "properties": {"user": {"$ref": "#/components/schemas/User"}, "session_id": {"type": "string"}, "mfa_required": {"type": "boolean", "description": "True when MFA is enrolled but not yet verified"}}},
    "OAuthStart": {"type": "object", "required": ["authorize_url"], "properties": {"authorize_url": {"type": "string"}, "state": {"type": "string"}}},
    "MfaEnrollment": {"type": "object", "required": ["secret_ref", "otpauth_url"], "properties": {"secret_ref": {"type": "string", "description": "Secret stored server-side; value never returned"}, "otpauth_url": {"type": "string"}}},
    "Session": {"type": "object", "required": ["id", "created_at"], "properties": {"id": {"type": "string"}, "device": {"type": "string"}, "ip": {"type": "string"}, "created_at": {"type": "string", "format": "date-time"}, "last_seen_at": {"type": "string", "format": "date-time"}}},
    "ApiToken": {"type": "object", "required": ["id", "name", "scopes"], "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "scopes": {"type": "array", "items": {"type": "string"}}, "created_at": {"type": "string", "format": "date-time"}, "expires_at": {"type": ["string", "null"], "format": "date-time"}, "last_used_at": {"type": ["string", "null"], "format": "date-time"}, "value": {"type": "string", "description": "Present only on creation response; never stored in plaintext"}}},
    "PermissionSet": {"type": "object", "required": ["permissions"], "properties": {"permissions": {"type": "array", "items": {"type": "string"}}, "roles": {"type": "array", "items": {"type": "string"}}, "cached_until": {"type": "string", "format": "date-time"}}},
    "Notification": {"type": "object", "required": ["id", "channel"], "properties": {"id": {"type": "string"}, "channel": {"type": "string"}, "events": {"type": "array", "items": {"type": "string"}}, "enabled": {"type": "boolean"}}},
    "Role": {"type": "object", "required": ["id", "name", "permissions"], "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "permissions": {"type": "array", "items": {"type": "string"}}, "created_at": {"type": "string", "format": "date-time"}}},
    "Invitation": {"type": "object", "required": ["id", "email", "role", "status"], "properties": {"id": {"type": "string"}, "email": {"type": "string", "format": "email"}, "role": {"type": "string"}, "status": {"enum": ["pending", "accepted", "expired"]}, "created_at": {"type": "string", "format": "date-time"}}},
    "Provider": {"type": "object", "required": ["id", "kind", "name", "status"], "properties": {"id": {"type": "string"}, "kind": {"type": "string"}, "name": {"type": "string"}, "status": {"enum": ["active", "degraded", "down"]}, "litellm_config_ref": {"type": "string"}, "last_probe": {"type": ["string", "null"], "format": "date-time"}}},
    "RoutingRule": {"type": "object", "required": ["id", "priority", "match", "target_alias"], "properties": {"id": {"type": "string"}, "priority": {"type": "integer"}, "match": {"type": "object"}, "target_alias": {"type": "string"}, "fallbacks": {"type": "array", "items": {"type": "string"}}, "status": {"enum": ["active", "retired"]}}},
    "RoutingPreview": {"type": "object", "required": ["resolved_alias"], "properties": {"resolved_alias": {"type": "string"}, "matched_rule_id": {"type": ["string", "null"]}, "chain": {"type": "array", "items": {"type": "string"}}}},
    "Integration": {"type": "object", "required": ["id", "kind", "status"], "properties": {"id": {"type": "string"}, "kind": {"type": "string"}, "status": {"enum": ["connected", "error", "disconnected"]}, "config": {"type": "object"}, "secret_refs": {"type": "array", "items": {"type": "string"}}}},
    "McpServer": {"type": "object", "required": ["id", "name", "transport", "endpoint"], "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "transport": {"enum": ["stdio", "streamable_http"]}, "endpoint": {"type": "string"}, "status": {"enum": ["connected", "error", "disabled"]}, "tool_count": {"type": "integer"}}},
    "Skill": {"type": "object", "required": ["id", "key", "instructions"], "properties": {"id": {"type": "string"}, "key": {"type": "string"}, "instructions": {"type": "string"}, "tools": {"type": "array", "items": {"type": "string"}}, "version": {"type": "integer"}, "status": {"enum": ["draft", "published", "retired"]}}},
    "KnowledgeSource": {"type": "object", "required": ["id", "kind", "status"], "properties": {"id": {"type": "string"}, "kind": {"type": "string"}, "config": {"type": "object"}, "status": {"enum": ["syncing", "synced", "error"]}, "last_sync_at": {"type": ["string", "null"], "format": "date-time"}}},
    "Document": {"type": "object", "required": ["id", "filename", "status"], "properties": {"id": {"type": "string"}, "filename": {"type": "string"}, "size_bytes": {"type": "integer"}, "content_type": {"type": "string"}, "status": {"enum": ["uploaded", "chunked", "indexed", "failed"]}, "indexed_version": {"type": "integer"}, "created_at": {"type": "string", "format": "date-time"}}},
    "PresignResult": {"type": "object", "required": ["upload_url"], "properties": {"upload_url": {"type": "string"}, "expires_at": {"type": "string", "format": "date-time"}, "max_size_bytes": {"type": "integer"}}},
    "RetrieveResult": {"type": "object", "required": ["hits"], "properties": {"hits": {"type": "array", "items": {"type": "object", "required": ["content", "score", "document_id"], "properties": {"content": {"type": "string"}, "score": {"type": "number"}, "document_id": {"type": "string"}, "permissions": {"type": "array", "items": {"type": "string"}}}}}, "took_ms": {"type": "integer"}}},
    "Schedule": {"type": "object", "required": ["id", "workflow_id", "cron", "status"], "properties": {"id": {"type": "string"}, "workflow_id": {"type": "string"}, "workflow_version": {"type": "integer"}, "cron": {"type": "string"}, "input": {"type": "object"}, "status": {"enum": ["active", "paused"]}, "next_run_at": {"type": ["string", "null"], "format": "date-time"}}},
    "Trigger": {"type": "object", "required": ["id", "event_type", "workflow_id"], "properties": {"id": {"type": "string"}, "event_type": {"type": "string"}, "filter": {"type": "object"}, "workflow_id": {"type": "string"}, "workflow_version": {"type": "integer"}, "status": {"enum": ["active", "paused"]}}},
    "Webhook": {"type": "object", "required": ["id", "events"], "properties": {"id": {"type": "string"}, "events": {"type": "array", "items": {"type": "string"}}, "url": {"type": "string"}, "secret_last4": {"type": "string"}, "created_at": {"type": "string", "format": "date-time"}}},
    "InboxItem": {"type": "object", "required": ["id", "kind", "title"], "properties": {"id": {"type": "string"}, "kind": {"enum": ["approval", "mention", "notification", "task"]}, "title": {"type": "string"}, "payload": {"type": "object"}, "read": {"type": "boolean"}, "created_at": {"type": "string", "format": "date-time"}}},
    "ActivityEvent": {"type": "object", "required": ["id", "type", "created_at"], "properties": {"id": {"type": "string"}, "type": {"type": "string"}, "actor": {"type": "string"}, "resource": {"type": "string"}, "created_at": {"type": "string", "format": "date-time"}}},
    "SearchResult": {"type": "object", "required": ["id", "kind", "title"], "properties": {"id": {"type": "string"}, "kind": {"enum": ["agent", "workflow", "run", "document", "collection"]}, "title": {"type": "string"}, "snippet": {"type": "string"}, "url": {"type": "string"}}},
    "Workspace": {"type": "object", "required": ["id", "name"], "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "settings": {"type": "object"}, "created_at": {"type": "string", "format": "date-time"}}},
    "SecretMeta": {"type": "object", "required": ["id", "name"], "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "kms_key_ref": {"type": "string"}, "created_at": {"type": "string", "format": "date-time"}, "rotated_at": {"type": ["string", "null"], "format": "date-time"}}},
    "HealthStatus": {"type": "object", "required": ["components"], "properties": {"components": {"type": "array", "items": {"type": "object", "required": ["name", "status"], "properties": {"name": {"type": "string"}, "status": {"enum": ["ok", "degraded", "down"]}, "detail": {"type": "string"}}}}}},
    "ValidationReport": {"type": "object", "required": ["valid", "issues"], "properties": {"valid": {"type": "boolean"}, "issues": {"type": "array", "items": {"type": "object", "required": ["path", "code", "message"], "properties": {"path": {"type": "string"}, "code": {"type": "string"}, "message": {"type": "string"}}}}}},
    "ToolTestResult": {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}, "output": {}, "error": {"type": ["string", "null"]}, "took_ms": {"type": "integer"}}},
    "ToolUsageStats": {"type": "object", "required": ["tool_id", "calls_7d"], "properties": {"tool_id": {"type": "string"}, "calls_7d": {"type": "integer"}, "errors_7d": {"type": "integer"}, "p95_latency_ms": {"type": "integer"}}},
    "BudgetReservation": {"type": "object", "required": ["run_id", "status", "reserved_usd"], "properties": {"run_id": {"type": "string"}, "status": {"enum": ["reserved", "settled", "released"]}, "reserved_usd": {"type": "number"}, "committed_usd": {"type": "number"}, "scopes": {"type": "array", "items": {"type": "string"}}}},
    "AnalyticsSeries": {"type": "object", "required": ["series"], "properties": {"series": {"type": "array", "items": {"type": "object", "required": ["ts", "value"], "properties": {"ts": {"type": "string", "format": "date-time"}, "value": {"type": "number"}, "dimensions": {"type": "object"}}}}, "totals": {"type": "object"}}},
    "AgentTemplate": {"type": "object", "required": ["id", "name", "config"], "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "description": {"type": "string"}, "config": {"$ref": "#/components/schemas/AgentConfig"}}},
    "Artifact": {"type": "object", "required": ["key", "url"], "properties": {"key": {"type": "string"}, "url": {"type": "string", "description": "Short-lived presigned URL"}, "size_bytes": {"type": "integer"}, "content_type": {"type": "string"}, "expires_at": {"type": "string", "format": "date-time"}}},
    "AuditExport": {"type": "object", "required": ["format", "download_url"], "properties": {"format": {"enum": ["jsonl", "csv"]}, "download_url": {"type": "string"}, "record_count": {"type": "integer"}, "expires_at": {"type": "string", "format": "date-time"}}},
    "WebhookTestResult": {"type": "object", "required": ["delivered"], "properties": {"delivered": {"type": "boolean"}, "status_code": {"type": ["integer", "null"]}, "response_excerpt": {"type": ["string", "null"]}}},
    "ExportBundle": {"type": "object", "required": ["bundle", "signature"], "properties": {"bundle": {"type": "object"}, "signature": {"type": "string"}}},
}

# Canonical workflow DSL: import the companion JSON Schema (single source of truth).
# $defs entries become component schemas; internal refs are rewritten accordingly.
import json as _json, copy as _copy
_wf = _json.load(open("companions/workflow-definition.schema.json"))
_wf_nodes = _wf.pop("$defs")
_wf.pop("$id", None); _wf.pop("$schema", None); _wf.pop("examples", None)
_wf_schemas = {}
for _k, _v in _wf_nodes.items():
    _wf_schemas[_k] = _copy.deepcopy(_v)
_wf_main = _copy.deepcopy(_wf)
def _rewrite(o):
    if isinstance(o, dict):
        return {k: ("#/components/schemas/" + v.split("/")[-1] if k == "$ref" and isinstance(v, str) and v.startswith("#/$defs/") else _rewrite(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [_rewrite(x) for x in o]
    return o
_wf_main = _rewrite(_wf_main)
_wf_schemas = {k: _rewrite(v) for k, v in _wf_schemas.items()}
schemas["WorkflowDefinition"] = _wf_main
for _k, _v in _wf_schemas.items():
    schemas.setdefault(_k, _v)
schemas["WorkflowDef"] = {"$ref": "#/components/schemas/WorkflowDefinition"}

doc = {
    "openapi": "3.1.0",
    "info": {"title": "AI Orchestration Platform API", "version": "0.1.0",
             "description": "Proposed v1 contract covering the full route inventory. The FastAPI application is the source of truth; this file is the pre-implementation reference contract."},
    "servers": [{"url": "https://api.example.com/api/v1"}],
    "security": [{"sessionCookie": []}, {"bearerToken": []}],
    "paths": paths,
    "components": {
        "securitySchemes": {
            "sessionCookie": {"type": "apiKey", "in": "cookie", "name": "sid"},
            "bearerToken": {"type": "http", "scheme": "bearer"}},
        "schemas": schemas,
        "responses": {
            "BadRequest": {"description": "Validation error", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
            "Unauthorized": {"description": "Not authenticated", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
            "Forbidden": {"description": "Missing permission", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
            "NotFound": {"description": "Not found", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
            "Conflict": {"description": "Idempotency / concurrency conflict", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
            "Unprocessable": {"description": "Semantically invalid (BUDGET_EXCEEDED, MODEL_CAPABILITY_MISMATCH, APPROVAL_STALE)", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
            "RateLimited": {"description": "Rate limited (Retry-After header)", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
        },
    },
}

with open("companions/openapi.yaml", "w") as f:
    yaml.safe_dump(doc, f, sort_keys=False, allow_unicode=True, width=100)

n = 0
for p, ops in paths.items():
    for k in ops:
        if k in ("get", "post", "put", "patch", "delete"):
            n += 1
print(f"openapi.yaml written: {len(paths)} paths, {n} operations")
