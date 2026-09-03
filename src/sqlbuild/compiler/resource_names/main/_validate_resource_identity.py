"""Canonical resource identity validation entrypoint."""

from __future__ import annotations

import re
from pathlib import Path

from sqlbuild.compiler.resource_names._helpers.spelling import suggest_resource_identity
from sqlbuild.compiler.resource_names.constants import (
    PRIVATE_SNAKE_CASE_PATTERN,
    SNAKE_CASE_PATTERN,
)
from sqlbuild.compiler.resource_names.exceptions import ResourceIdentityError


def validate_resource_identity(
    *, name: str, kind: str, path: Path, private_identity: bool = False
) -> None:
    """Reject one identity unless it uses canonical lowercase snake_case."""

    pattern: re.Pattern[str] = (
        PRIVATE_SNAKE_CASE_PATTERN if private_identity else SNAKE_CASE_PATTERN
    )
    if pattern.fullmatch(name) is not None:
        return
    corrected_name: str = suggest_resource_identity(name=name, private_identity=private_identity)
    raise ResourceIdentityError(
        f"Invalid {kind} identity '{name}' in {path}; use snake_case '{corrected_name}'",
        help=(
            "Rename the authored identity and update its references, selectors, and integration "
            "keys. SQLBuild does not silently normalize resource identities. Double underscores "
            "remain valid."
        ),
    )
