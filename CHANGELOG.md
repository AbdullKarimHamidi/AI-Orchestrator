# Changelog

## 0.3.1

- User guide with screenshots: `docs/user-guide.pdf`.
- Built-in knowledge search now matches word forms ("refund" finds "Refunds") and ignores filler words.
  Reindex documents added with 0.3.0 to benefit.
- Knowledge base document and chunk counts refresh as soon as ingestion finishes.

## 0.3.0

- Tools: HTTP API tools and tools imported from remote MCP servers, with encrypted secret headers,
  JSON Schema validation, timeouts, response-size caps and an SSRF guard. Test console per tool.
- Tool calling for OpenAI, Anthropic, Gemini and OpenAI-compatible models; `limits.max_tool_calls` per agent.
- Knowledge (RAG): knowledge bases, file upload (PDF, DOCX, Markdown, HTML, CSV, JSON, text) or pasted
  text, ingestion in the worker, provider embeddings or a built-in lexical index, search test,
  citations in run output. Agents pick knowledge bases and `knowledge_top_k`.
- Run timeline shows tool calls, tool results and retrieved passages.

## 0.2.0

- Fixed: missing `.env.example`, API crash on `CORS_ORIGINS`, worker always reported unhealthy.
- Teams: invitation links, closed registration, several workspaces per user, password change, operator CLI.
- Workspace API keys and synchronous runs (`POST /runs?wait_seconds=`).
- Production: Caddy HTTPS overlay, backups and restore, CI workflow, deployment guide.
