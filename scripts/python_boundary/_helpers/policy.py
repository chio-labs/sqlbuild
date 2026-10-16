"""Read and validate the Python boundary policy file."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

from scripts.python_boundary.constants import (
    ESCAPING_PATH_PARTS,
    NOTE_RULE_PATTERN,
    SOURCE_ROOT,
    STAY_KEYS,
    STAY_RULES,
)
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
                rule=entry.get("rule"),
                note=str(entry.get("note", "")),
                unknown_keys=tuple(sorted(set(entry) - STAY_KEYS)),
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
        parts: tuple[str, ...] = Path(entry.path).parts
        if not parts or Path(entry.path).is_absolute() or set(parts) & ESCAPING_PATH_PARTS:
            errors.append(f"stays entry {entry.path!r} must name a module under {SOURCE_ROOT}.")
        elif not (source / entry.path).exists():
            errors.append(f"stays entry {entry.path!r} does not exist under {SOURCE_ROOT}.")
        errors.extend(_stay_rule_errors(entry))
    for handler in policy.handled_native_errors:
        if not handler.note.strip():
            errors.append(f"handled_native_errors entry {handler.location!r} needs a note.")
    return tuple(errors)


def _stay_rule_errors(entry: StayEntry) -> tuple[str, ...]:
    """Errors for a stays entry without exactly one valid rule backed by a note."""
    errors: list[str] = []
    choices: str = "; ".join(f"{number} = {meaning}" for number, meaning in STAY_RULES.items())
    if entry.unknown_keys:
        errors.append(
            f"stays entry {entry.path!r} has unknown key(s) {', '.join(entry.unknown_keys)}; "
            "an entry has only path, rule and note."
        )
    rule: object = entry.rule
    if rule is None:
        errors.append(f"stays entry {entry.path!r} needs a rule: one of {choices}.")
    elif isinstance(rule, bool) or not isinstance(rule, int) or rule not in STAY_RULES:
        errors.append(f"stays entry {entry.path!r} has rule {rule!r}; use one of {choices}.")
    if not entry.note.strip():
        errors.append(f"stays entry {entry.path!r} needs a note with the evidence for its rule.")
    cited: set[int] = {int(number) for number in re.findall(NOTE_RULE_PATTERN, entry.note)}
    if isinstance(rule, int) and not isinstance(rule, bool) and cited - {rule}:
        errors.append(
            f"stays entry {entry.path!r} has rule {rule} but its note cites rule "
            f"{', '.join(str(number) for number in sorted(cited - {rule}))}."
        )
    return tuple(errors)
