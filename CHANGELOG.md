# Changelog

## Unreleased

- Free AI providers: one-step setup for Groq, Google Gemini, Cerebras, OpenRouter (`:free` models), Mistral and
  local Ollama, from `.env` (`GROQ_API_KEY`, `GEMINI_API_KEY`, ... `OLLAMA_BASE_URL`) or Models → Free AI providers.
  Keys set in `.env` are read at call time and never stored in the database.
- Starter agents: 8 ready-to-run agents in every new workspace, on the best connected free provider with the
  others as fallbacks (Demo when none). Agents → Install starter agents, or `python -m app.cli setup-free`.
- Providers now carry suggested models for the model picker without restricting them like an allowlist.

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
