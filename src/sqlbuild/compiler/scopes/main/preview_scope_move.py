"""Public pure resource move preview operation."""

from pathlib import PurePath

from sqlbuild.compiler.scopes._helpers.report_operations import build_move_preview
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

    return build_move_preview(lookup=lookup, resource=resource, destination=destination)
