"""Classify an authored path by the named declaration role that contains it."""

from __future__ import annotations

from pathlib import PurePath

from sqlbuild.compiler.scopes.constants import (
    DECLARATION_GROUP_DIRECTORY,
    GLOBAL_NAMED_DECLARATION_ROOTS,
    GROUPED_NAMED_DECLARATION_ROLES,
)
from sqlbuild.compiler.scopes.types import DeclarationKind, ScopeKind


def named_declaration_role_kind(*, relative_path: PurePath) -> DeclarationKind | None:
    """Return the audit, schema, or hook kind for a project-relative declaration file path."""

    parts: tuple[str, ...] = relative_path.parts[:-1]
    for role_parts, kind in GLOBAL_NAMED_DECLARATION_ROOTS.items():
        if parts[: len(role_parts)] == role_parts:
            return kind
    for index, part in enumerate(parts):
        if part != DECLARATION_GROUP_DIRECTORY:
            continue
        grouped_role: tuple[str, ...]
        role: tuple[DeclarationKind, ScopeKind]
        for grouped_role, role in GROUPED_NAMED_DECLARATION_ROLES.items():
            if parts[index + 1 : index + 1 + len(grouped_role)] == grouped_role:
                return role[0]
    return None
