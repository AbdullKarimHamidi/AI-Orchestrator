"""Structured JSON logging with request correlation and secret redaction."""
import contextvars
import json
import logging
import re
import sys
from datetime import UTC, datetime

correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="-")

_SECRET_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9_\-]{8,})"),
    re.compile(r"(sk-ant-[A-Za-z0-9_\-]{8,})"),
    re.compile(r"(AIza[0-9A-Za-z_\-]{20,})"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}"),
]
_SECRET_KEYS = {"api_key", "password", "authorization", "x-api-key", "token", "secret", "api_key_enc"}


def redact_text(text: str) -> str:
    for pat in _SECRET_PATTERNS:
        text = pat.sub(lambda m: (m.group(1) if m.lastindex and m.group(1).lower().startswith("bearer") else "")
                       + "[REDACTED]", text)
    return text


def redact(value: object) -> object:
    """Recursively redact secret-looking keys and values (used for logs and run events)."""
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if str(k).lower() in _SECRET_KEYS else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact_text(record.getMessage()),
            "correlation_id": correlation_id.get(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(redact(extra))  # type: ignore[arg-type]
        if record.exc_info:
            payload["exc"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    logging.getLogger("httpx").setLevel("WARNING")
