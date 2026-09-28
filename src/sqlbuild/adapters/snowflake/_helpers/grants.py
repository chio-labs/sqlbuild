"""Read and replay Snowflake grants onto a compatibility view."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.models import RelationGrant
from sqlbuild.adapter.contract.types import RelationType
from sqlbuild.adapter.type_system.main.normalize_relation_type import normalize_relation_type

_VIEW_PRIVILEGES: frozenset[str] = frozenset({"SELECT", "REFERENCES"})
_GRANTEE_KEYWORDS: dict[str, str] = {"ROLE": "ROLE", "DATABASE_ROLE": "DATABASE ROLE"}
_PRIVILEGE_COLUMN: int = 1
_GRANTED_TO_COLUMN: int = 4
_GRANTEE_COLUMN: int = 5
_GRANT_OPTION_COLUMN: int = 6
_GRANT_OPTIONS: dict[str, bool] = {"true": True}
_OBJECT_KEYWORDS: dict[RelationType, str] = {RelationType.VIEW: "VIEW"}


def snowflake_relation_grants(rows: list[tuple[Any, ...]]) -> tuple[RelationGrant, ...]:
    """Keep SHOW GRANTS rows that apply to a view, skipping OWNERSHIP and shares."""

    grants: list[RelationGrant] = []
    row: tuple[Any, ...]
    for row in rows:
        privilege: str = str(row[_PRIVILEGE_COLUMN]).upper()
        keyword: str | None = _GRANTEE_KEYWORDS.get(str(row[_GRANTED_TO_COLUMN]).upper())
        if privilege not in _VIEW_PRIVILEGES or keyword is None:
            continue
        grants.append(
            RelationGrant(
                privilege=privilege,
                grantee=str(row[_GRANTEE_COLUMN]),
                grantable=_GRANT_OPTIONS.get(str(row[_GRANT_OPTION_COLUMN]).lower(), False),
                grantee_kind=keyword,
            )
        )
    return tuple(grants)


def render_snowflake_view_grants(
    *, grants: tuple[RelationGrant, ...], destination: str
) -> tuple[str, ...]:
    """Render role and database-role grants on ``destination``."""

    return tuple(
        f"GRANT {grant.privilege} ON VIEW {destination} TO {grant.grantee_kind} "
        + _quoted_grantee(grant.grantee or "")
        + (" WITH GRANT OPTION" if grant.grantable else "")
        for grant in grants
    )


def render_snowflake_view_revokes(
    *, grants: tuple[RelationGrant, ...], destination: str
) -> tuple[str, ...]:
    """Render role and database-role grants to remove from ``destination``."""

    return tuple(
        f"REVOKE {grant.privilege} ON VIEW {destination} FROM {grant.grantee_kind} "
        + _quoted_grantee(grant.grantee or "")
        for grant in grants
    )


def _quoted_grantee(grantee: str) -> str:
    return ".".join('"' + part.replace('"', '""') + '"' for part in grantee.split("."))


def show_grants_object_kind(relation_type: str) -> str:
    """Return the SHOW GRANTS object keyword for a listed relation type."""

    return _OBJECT_KEYWORDS.get(normalize_relation_type(relation_type), "TABLE")
