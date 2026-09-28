"""Render Unity Catalog grants replayed onto a compatibility view."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.types import RelationType
from sqlbuild.adapter.type_system.main.normalize_relation_type import normalize_relation_type

_VIEW_PRIVILEGES: frozenset[str] = frozenset({"SELECT", "APPLY TAG", "ALL PRIVILEGES", "MANAGE"})
_OBJECT_TYPES: frozenset[str] = frozenset({"TABLE", "VIEW"})
_PRINCIPAL_COLUMN: int = 0
_ACTION_COLUMN: int = 1
_OBJECT_TYPE_COLUMN: int = 2
_OBJECT_KEYWORDS: dict[RelationType, str] = {RelationType.VIEW: "VIEW"}


def render_databricks_view_grants(
    *, rows: list[tuple[Any, ...]], destination: str
) -> tuple[str, ...]:
    """Replay privileges granted on the relation itself that also apply to a view."""

    statements: list[str] = []
    row: tuple[Any, ...]
    for row in rows:
        action: str = str(row[_ACTION_COLUMN]).upper()
        if (
            action not in _VIEW_PRIVILEGES
            or str(row[_OBJECT_TYPE_COLUMN]).upper() not in _OBJECT_TYPES
        ):
            continue
        principal: str = "`" + str(row[_PRINCIPAL_COLUMN]).replace("`", "``") + "`"
        statements.append(f"GRANT {action} ON VIEW {destination} TO {principal}")
    return tuple(statements)


def show_grants_object_kind(relation_type: str) -> str:
    """Return the SHOW GRANTS object keyword for a listed relation type."""

    return _OBJECT_KEYWORDS.get(normalize_relation_type(relation_type), "TABLE")
