"""Pure-ASGI middleware (works with streaming responses such as SSE)."""
import json
import re
import secrets

from app.core.config import get_settings
from app.core.ids import new_id
from app.core.logging import correlation_id

_SAFE_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_EXEMPT = {"/api/v1/auth/login", "/api/v1/auth/register"}


async def _send_error(send, status: int, code: str, message: str) -> None:
    body = json.dumps({"error": {"code": code, "message": message, "details": {},
                                 "correlation_id": correlation_id.get()}}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"x-request-id", correlation_id.get().encode())]})
    await send({"type": "http.response.body", "body": body})


class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        incoming = headers.get(b"x-request-id", b"").decode()
        cid = incoming if _SAFE_ID.match(incoming or "") else new_id("req")
        token = correlation_id.set(cid)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + [
                    (b"x-request-id", cid.encode()), (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"), (b"cache-control", b"no-store")]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            correlation_id.reset(token)


class BodySizeLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        s = get_settings()
        # Document uploads get their own (larger) limit; everything else stays small.
        limit = s.max_upload_bytes + 100_000 if scope["path"].endswith("/documents/upload") else s.max_request_bytes
        cl = dict(scope["headers"]).get(b"content-length")
        if cl and cl.isdigit() and int(cl) > limit:
            return await _send_error(send, 413, "PAYLOAD_TOO_LARGE", f"Request body exceeds {limit} bytes")
        received = 0

        async def limited_receive():
            nonlocal received
            msg = await receive()
            if msg["type"] == "http.request":
                received += len(msg.get("body", b""))
                if received > limit:
                    raise ValueError("payload too large")
            return msg

        try:
            await self.app(scope, limited_receive, send)
        except ValueError as exc:
            if str(exc) == "payload too large":
                return await _send_error(send, 413, "PAYLOAD_TOO_LARGE", f"Request body exceeds {limit} bytes")
            raise


class CSRFMiddleware:
    """Double-submit cookie: state-changing requests that carry a session cookie must send
    X-CSRF-Token equal to the csrf cookie. Combined with SameSite=Lax session cookies."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in SAFE_METHODS or scope["path"] in CSRF_EXEMPT:
            return await self.app(scope, receive, send)
        s = get_settings()
        headers = dict(scope["headers"])
        cookies = _parse_cookies(headers.get(b"cookie", b"").decode())
        if s.session_cookie_name in cookies:
            sent = headers.get(b"x-csrf-token", b"").decode()
            expected = cookies.get(s.csrf_cookie_name, "")
            if not expected or not sent or not secrets.compare_digest(sent, expected):
                return await _send_error(send, 403, "CSRF_FAILED", "Missing or invalid CSRF token")
        return await self.app(scope, receive, send)


def _parse_cookies(raw: str) -> dict[str, str]:
    out = {}
    for part in raw.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            out[k] = v
    return out
