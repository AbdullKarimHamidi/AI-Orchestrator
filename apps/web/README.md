# Web app

Next.js 16 frontend of the orchestration platform. It contains no business logic: every `/api/*` request is
proxied to FastAPI (see `next.config.ts`). Setup, scripts and deployment are documented in the
[root README](../../README.md).

```bash
npm ci
npm run dev        # http://localhost:3000 (expects the API on http://127.0.0.1:8000, override with API_INTERNAL_URL)
npm run typecheck && npm run lint && npm test && npm run build
npm run e2e        # Playwright against a running stack; set PW_CHROMIUM_PATH to reuse an installed Chromium
```
