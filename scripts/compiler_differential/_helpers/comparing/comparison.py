"""Read the diagnostics of a JSON compile report."""

from __future__ import annotations

import json

from scripts.compiler_differential._helpers.comparing.compare import as_json_object
from scripts.compiler_differential.models import CommandOutcome


def diagnostic_codes(*, outcome: CommandOutcome, severity: str | None) -> tuple[str, ...]:
    """Return a JSON compile report's diagnostic codes in order, optionally of one severity."""

    return tuple(
        str(diagnostic.get("code"))
        for diagnostic in _diagnostics(outcome=outcome, severity=severity)
    )


def first_diagnostic_message(*, outcome: CommandOutcome, severity: str) -> str | None:
    """Return the message of a JSON compile report's first diagnostic of one severity."""

    diagnostics: list[dict[str, object]] = _diagnostics(outcome=outcome, severity=severity)
    return str(diagnostics[0].get("message")) if diagnostics else None


def first_diagnostic(*, outcome: CommandOutcome, severity: str) -> dict[str, object]:
    """Return a JSON compile report's first diagnostic of one severity, or an empty mapping."""

    diagnostics: list[dict[str, object]] = _diagnostics(outcome=outcome, severity=severity)
    return diagnostics[0] if diagnostics else {}


def _diagnostics(*, outcome: CommandOutcome, severity: str | None) -> list[dict[str, object]]:
    payload: dict[str, object] = as_json_object(_loads(outcome.stdout)) or {}
    diagnostics: object = payload.get("diagnostics")
    found: list[dict[str, object]] = []
    for raw_diagnostic in diagnostics if isinstance(diagnostics, list) else ():
        diagnostic: dict[str, object] | None = as_json_object(raw_diagnostic)
        if diagnostic is not None and (severity is None or diagnostic.get("severity") == severity):
            found.append(diagnostic)
    return found


def _loads(text: str | None) -> object:
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
