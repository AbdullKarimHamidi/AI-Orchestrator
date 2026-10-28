"""Minimal, sandboxed templates for workflows: ``{{ dotted.path }}`` lookups only.

There are no expressions, filters or attribute calls, so a template cannot execute code.
Unknown paths raise TemplateError instead of rendering as empty text (strict, like Jinja's
StrictUndefined), so a typo fails the run visibly rather than sending a blank prompt.
"""
import json
import re
from typing import Any

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_\-]*(?:\.[A-Za-z0-9_\-]+)*)\s*\}\}")


class TemplateError(Exception):
    pass


def lookup(ctx: dict, path: str) -> Any:
    cur: Any = ctx
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            raise TemplateError(f"unknown template variable '{path}'")
    return cur


def _text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False, default=str)


def render(template: str, ctx: dict) -> str:
    return _PLACEHOLDER.sub(lambda m: _text(lookup(ctx, m.group(1))), template)


def render_value(value: Any, ctx: dict) -> Any:
    """Renders strings inside nested dicts/lists. A string that is exactly one placeholder keeps
    the referenced value's type (so a tool argument can receive a number or an object)."""
    if isinstance(value, str):
        whole = _PLACEHOLDER.fullmatch(value.strip())
        if whole:
            return lookup(ctx, whole.group(1))
        return render(value, ctx)
    if isinstance(value, dict):
        return {k: render_value(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [render_value(v, ctx) for v in value]
    return value


def variables(template: str) -> list[str]:
    return [m.group(1) for m in _PLACEHOLDER.finditer(template)]
