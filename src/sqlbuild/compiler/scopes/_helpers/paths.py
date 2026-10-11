"""Project-relative scope path normalization, answered by the native scope paths."""

from __future__ import annotations

from pathlib import PurePath

import sqlbuild._native as _native
from sqlbuild.compiler.scopes.exceptions import InvalidScopePathError


def normalize_path(*, path: str | PurePath) -> str:
    """The canonical project-relative POSIX path; absolute or escaping paths raise."""

    normalized, error = _native.scope_normalize_path(str(path))
    if normalized is None:
        raise InvalidScopePathError(error or "")
    return normalized
