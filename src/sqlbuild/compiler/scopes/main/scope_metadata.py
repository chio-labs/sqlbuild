"""Public value-safe projection and serialization of canonical compiler scope facts."""

from __future__ import annotations

from sqlbuild.compiler.scopes._helpers.report_projection import build_projection
from sqlbuild.compiler.scopes.models import ScopeIndex
from sqlbuild.compiler.scopes.types import JsonValue


def scope_metadata_projection(*, index: ScopeIndex) -> dict[str, JsonValue]:
    """Return deterministic, value-free scope metadata for external consumers."""

    return build_projection(index=index)
