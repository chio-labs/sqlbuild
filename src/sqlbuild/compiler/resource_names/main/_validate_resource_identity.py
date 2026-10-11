"""Canonical resource identity validation entrypoint."""

from __future__ import annotations

from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.resource_names.exceptions import ResourceIdentityError


def validate_resource_identity(
    *, name: str, kind: str, path: Path, private_identity: bool = False
) -> None:
    """Reject one identity unless it uses canonical lowercase snake_case."""

    failure: tuple[str, str] | None = _native.resource_identity_suggestion(name, private_identity)
    if failure is None:
        return
    corrected_name, help_text = failure
    raise ResourceIdentityError(
        f"Invalid {kind} identity '{name}' in {path}; use snake_case '{corrected_name}'",
        help=help_text,
    )
