"""Helpers for rendering project variable values in text contexts."""

from __future__ import annotations

import json

from sqlbuild.shared.exceptions.errors import SharedInputError

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
        raise SharedInputError(
            f"{label} is an object and cannot be interpolated as text: "
            f"{_preview_json(value)}. Use a macro to consume structured vars."
        )
    if isinstance(value, list):
        raise SharedInputError(
            f"{label} is an array and cannot be interpolated as text: "
            f"{_preview_json(value)}. Use a macro to consume structured vars."
        )
    raise SharedInputError(
        f"{label} has unsupported type {type(value).__name__!r} and cannot be interpolated as text"
    )


def _preview_json(value: object) -> str:
    preview: str = json.dumps(value, separators=(",", ":"), sort_keys=True)
    if len(preview) <= _PREVIEW_LIMIT:
        return preview
    return f"{preview[: _PREVIEW_LIMIT - 3]}..."
