"""Helpers for rendering project variable values in text contexts."""

from __future__ import annotations

import json

_PREVIEW_LIMIT: int = 120


def render_project_var_text(*, value: object, label: str) -> str:
    """Render one project var value for SQL/config text interpolation."""

    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str | int | float):
        return str(value)
    if isinstance(value, dict):
        raise ValueError(
            f"{label} is an object and cannot be interpolated as text: "
            f"{_preview_json(value)}. Use a macro to consume structured vars."
        )
    if isinstance(value, list):
        raise ValueError(
            f"{label} is an array and cannot be interpolated as text: "
            f"{_preview_json(value)}. Use a macro to consume structured vars."
        )
    raise ValueError(
        f"{label} has unsupported type {type(value).__name__!r} and cannot be interpolated as text"
    )


def _preview_json(value: object) -> str:
    preview: str = json.dumps(value, separators=(",", ":"), sort_keys=True)
    if len(preview) <= _PREVIEW_LIMIT:
        return preview
    return f"{preview[: _PREVIEW_LIMIT - 3]}..."
