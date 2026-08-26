"""Normalize one project-relative scope path."""

from __future__ import annotations

from pathlib import PurePath

from sqlbuild.compiler.scopes._helpers.paths import normalize_path


def normalize_scope_path(*, path: str | PurePath) -> str:
    """Normalize POSIX or Windows input to a project-relative POSIX path."""

    return normalize_path(path=path)
