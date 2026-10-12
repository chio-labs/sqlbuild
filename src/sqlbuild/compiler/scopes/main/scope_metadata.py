"""Public value-safe projection and serialization of canonical compiler scope facts."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.scopes.models import ScopeIndex
from sqlbuild.compiler.scopes.types import JsonValue


def scope_metadata_projection(*, index: ScopeIndex) -> dict[str, JsonValue]:
    """Return deterministic, value-free scope metadata for external consumers."""

    return _native.scope_metadata_projection(index)
