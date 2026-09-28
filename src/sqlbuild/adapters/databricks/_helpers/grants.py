"""Read and replay Unity Catalog grants onto a compatibility view."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.models import RelationGrant
from sqlbuild.adapter.contract.types import RelationType
from sqlbuild.adapter.type_system.main.normalize_relation_type import normalize_relation_type

_VIEW_PRIVILEGES: frozenset[str] = frozenset({"SELECT", "APPLY TAG", "ALL PRIVILEGES", "MANAGE"})
_OBJECT_TYPES: frozenset[str] = frozenset({"TABLE", "VIEW"})
_PRINCIPAL_COLUMN: int = 0
_ACTION_COLUMN: int = 1
_OBJECT_TYPE_COLUMN: int = 2
_OBJECT_KEYWORDS: dict[RelationType, str] = {RelationType.VIEW: "VIEW"}


def databricks_relation_grants(rows: list[tuple[Any, ...]]) -> tuple[RelationGrant, ...]:
    """Keep privileges granted on the relation itself that also apply to a view."""

    return tuple(
        RelationGrant(
            privilege=str(row[_ACTION_COLUMN]).upper(), grantee=str(row[_PRINCIPAL_COLUMN])
        )
        for row in rows
        if str(row[_ACTION_COLUMN]).upper() in _VIEW_PRIVILEGES
        and str(row[_OBJECT_TYPE_COLUMN]).upper() in _OBJECT_TYPES
    )


def render_databricks_view_grants(
    *, grants: tuple[RelationGrant, ...], destination: str
) -> tuple[str, ...]:
    """Render Unity Catalog grants on ``destination``."""

    return tuple(
        f"GRANT {grant.privilege} ON VIEW {destination} TO "
        + "`"
        + (grant.grantee or "").replace("`", "``")
        + "`"
        for grant in grants
    )


def render_databricks_view_revokes(
    *, grants: tuple[RelationGrant, ...], destination: str
) -> tuple[str, ...]:
    """Render Unity Catalog grants to remove from ``destination``."""

    return tuple(
        f"REVOKE {grant.privilege} ON VIEW {destination} FROM "
        + "`"
        + (grant.grantee or "").replace("`", "``")
        + "`"
        for grant in grants
    )


def show_grants_object_kind(relation_type: str) -> str:
    """Return the SHOW GRANTS object keyword for a listed relation type."""

    return _OBJECT_KEYWORDS.get(normalize_relation_type(relation_type), "TABLE")
