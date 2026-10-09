"""Project-relative normalization of authored scope paths."""

from __future__ import annotations

from pathlib import PurePath

from sqlbuild.compiler.scopes._helpers.paths import normalize_path


def normalize_scope_path(*, path: str | PurePath) -> str:
    """Return `path` normalized, raising when it is not project-relative."""

    return normalize_path(path=path)
