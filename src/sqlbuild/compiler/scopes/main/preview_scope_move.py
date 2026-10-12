"""Public pure resource move preview operation."""

from pathlib import PurePath

import sqlbuild._native as _native
from sqlbuild.compiler.scopes.models import (
    MovePreview,
    ResourceIdentity,
    ScopeDiagnostic,
    ScopeLookup,
)


def preview_scope_move(
    *, lookup: ScopeLookup, resource: str | ResourceIdentity, destination: str | PurePath
) -> tuple[MovePreview | None, tuple[ScopeDiagnostic, ...]]:
    """Preview declaration visibility changes without mutating compiler facts."""

    return _native.scope_move_preview(lookup, resource, destination)
