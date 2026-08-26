"""Project safe default metadata from a scope index."""

from __future__ import annotations

from sqlbuild.compiler.scopes._helpers.projection import build_projection
from sqlbuild.compiler.scopes.models import ScopeIndex
from sqlbuild.compiler.scopes.types import JsonValue


def scope_metadata_projection(*, index: ScopeIndex) -> dict[str, JsonValue]:
    """Project stable index metadata without source bodies or constant values."""

    return build_projection(index=index)
