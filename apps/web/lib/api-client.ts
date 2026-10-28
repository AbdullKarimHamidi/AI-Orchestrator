/**
 * The single HTTP boundary between the UI and the FastAPI backend.
 *
 * - Same-origin: requests go to /api/v1/*, which Next.js rewrites to FastAPI, so the
 *   HttpOnly session cookie stays first-party. No secrets ever live in the browser.
 * - CSRF: mutating requests echo the readable csrf cookie in X-CSRF-Token.
 * - Workspace: X-Workspace-Id selects the workspace; FastAPI verifies membership.
 * - Every response is validated with a Zod schema; errors become ApiError.
 */
import type { z } from "zod"

export const API_BASE = "/api/v1"
const WS_STORAGE_KEY = "orch.workspace_id"

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
    public correlationId?: string,
  ) {
    super(message)
    this.name = "ApiError"
  }
}

export function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`))
  return match ? decodeURIComponent(match.slice(name.length + 1)) : undefined
}

let currentWorkspaceId: string | null = null

export function setWorkspaceId(id: string | null) {
  currentWorkspaceId = id
  if (typeof window !== "undefined") {
    if (id) window.localStorage.setItem(WS_STORAGE_KEY, id)
    else window.localStorage.removeItem(WS_STORAGE_KEY)
  }
}

export function getWorkspaceId(): string | null {
  if (currentWorkspaceId) return currentWorkspaceId
  if (typeof window !== "undefined") currentWorkspaceId = window.localStorage.getItem(WS_STORAGE_KEY)
  return currentWorkspaceId
}

type Method = "GET" | "POST" | "PATCH" | "DELETE"

interface RequestOptions {
  body?: unknown
  /** multipart upload; sent as-is (the browser sets the boundary) */
  form?: FormData
  query?: Record<string, string | number | undefined | null>
  headers?: Record<string, string>
  signal?: AbortSignal
}

async function request<T>(method: Method, path: string, schema: z.ZodType<T> | null, opts: RequestOptions = {}) {
  const url = new URL(API_BASE + path, typeof window === "undefined" ? "http://localhost" : window.location.origin)
  for (const [k, v] of Object.entries(opts.query ?? {})) if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v))
  const headers: Record<string, string> = { Accept: "application/json", ...opts.headers }
  if (opts.body !== undefined && !opts.form) headers["Content-Type"] = "application/json"
  if (method !== "GET") {
    const csrf = readCookie("orch_csrf")
    if (csrf) headers["X-CSRF-Token"] = csrf
  }
  const ws = getWorkspaceId()
  if (ws) headers["X-Workspace-Id"] = ws

  let res: Response
  try {
    res = await fetch(url.pathname + url.search, {
      method,
      headers,
      body: opts.form ?? (opts.body === undefined ? undefined : JSON.stringify(opts.body)),
      credentials: "same-origin",
      signal: opts.signal,
    })
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e
    throw new ApiError(0, "NETWORK_ERROR", "Cannot reach the API. Is the backend running?")
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  let json: unknown = undefined
  try {
    json = text ? JSON.parse(text) : undefined
  } catch {
    throw new ApiError(res.status, "BAD_RESPONSE", `Unexpected non-JSON response (HTTP ${res.status})`)
  }
  if (!res.ok) {
    const err = (json as { error?: { code: string; message: string; details?: Record<string, unknown>; correlation_id?: string } })?.error
    throw new ApiError(res.status, err?.code ?? "HTTP_ERROR", err?.message ?? `Request failed (HTTP ${res.status})`, err?.details ?? {}, err?.correlation_id)
  }
  if (!schema) return json as T
  const parsed = schema.safeParse(json)
  if (!parsed.success) {
    console.error("API contract mismatch", path, parsed.error.issues)
    throw new ApiError(res.status, "CONTRACT_MISMATCH", "The server response did not match the expected format")
  }
  return parsed.data
}

export const api = {
  get: <T>(path: string, schema: z.ZodType<T>, opts?: RequestOptions) => request("GET", path, schema, opts),
  post: <T>(path: string, schema: z.ZodType<T> | null, body?: unknown, opts?: RequestOptions) =>
    request("POST", path, schema, { ...opts, body: body ?? {} }),
  patch: <T>(path: string, schema: z.ZodType<T>, body: unknown, opts?: RequestOptions) =>
    request("PATCH", path, schema, { ...opts, body }),
  delete: (path: string, opts?: RequestOptions) => request<void>("DELETE", path, null, opts),
  upload: <T>(path: string, schema: z.ZodType<T>, form: FormData, opts?: RequestOptions) => request("POST", path, schema, { ...opts, form }),
}

/** URL for Server-Sent Events. EventSource cannot set headers, so the workspace goes in the
 * query string; FastAPI verifies membership exactly as it does for the header. */
export function streamUrl(path: string, after = 0): string {
  const qs = new URLSearchParams({ after: String(after) })
  const ws = getWorkspaceId()
  if (ws) qs.set("workspace_id", ws)
  return `${API_BASE}${path}?${qs}`
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message
  if (e instanceof Error) return e.message
  return "Something went wrong"
}
