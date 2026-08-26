"""Resolve path-derived lexical scope visibility."""

from __future__ import annotations

from pathlib import PurePath

from sqlbuild.compiler.scopes._helpers.paths import is_equal_or_descendant, normalize_path
from sqlbuild.compiler.scopes.constants import CURRENT_PATH_COMPONENT, PATH_SEPARATOR
from sqlbuild.compiler.scopes.types import ScopeKind


def scope_is_path_visible(
    *, scope: ScopeKind, owning_path: str | PurePath, resource_path: str | PurePath
) -> bool:
    """Resolve path-derived visibility without project discovery or I/O."""

    if scope is ScopeKind.GLOBAL:
        return True
    owner: str = normalize_path(path=owning_path)
    resource: str = normalize_path(path=resource_path)
    resource_parent: str = (
        resource.rsplit(PATH_SEPARATOR, maxsplit=1)[0]
        if PATH_SEPARATOR in resource
        else CURRENT_PATH_COMPONENT
    )
    if scope is ScopeKind.INHERITED:
        return is_equal_or_descendant(path=resource_parent, ancestor=owner)
    if scope is ScopeKind.LOCAL:
        return resource_parent == owner
    return False
