"""Read and validate the Python boundary policy file."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from scripts.python_boundary.constants import SOURCE_ROOT, STAY_REASONS
from scripts.python_boundary.models import BoundaryPolicy, ReviewedNativeHandler, StayEntry


def read_boundary_policy(path: Path) -> BoundaryPolicy:
    """Return the policy stored at `path`."""
    with path.open("rb") as handle:
        document: dict[str, Any] = tomllib.load(handle)
    return BoundaryPolicy(
        remaining_lines=int(document.get("remaining_lines", -1)),
        stays=tuple(
            StayEntry(
                path=str(entry.get("path", "")),
                reason=str(entry.get("reason", "")),
                note=str(entry.get("note", "")),
            )
            for entry in document.get("stays", ())
        ),
        handled_native_errors=tuple(
            ReviewedNativeHandler(
                location=str(entry.get("location", "")), note=str(entry.get("note", ""))
            )
            for entry in document.get("handled_native_errors", ())
        ),
    )


def get_policy_errors(*, root: Path, policy: BoundaryPolicy) -> tuple[str, ...]:
    """Return every malformed or stale policy entry."""
    source: Path = root / SOURCE_ROOT
    errors: list[str] = []
    if policy.remaining_lines < 0:
        errors.append("remaining_lines must be a non-negative integer.")
    seen: set[str] = set()
    for entry in policy.stays:
        if entry.path in seen:
            errors.append(f"stays lists {entry.path!r} more than once.")
        seen.add(entry.path)
        if not (source / entry.path).exists():
            errors.append(f"stays entry {entry.path!r} does not exist under {SOURCE_ROOT}.")
        if entry.reason not in STAY_REASONS:
            errors.append(
                f"stays entry {entry.path!r} has reason {entry.reason!r}; "
                f"use one of {', '.join(STAY_REASONS)}."
            )
        if not entry.note.strip():
            errors.append(f"stays entry {entry.path!r} needs a note explaining why it stays.")
    for handler in policy.handled_native_errors:
        if not handler.note.strip():
            errors.append(f"handled_native_errors entry {handler.location!r} needs a note.")
    return tuple(errors)
