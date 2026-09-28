"""Render Snowflake grants replayed onto a compatibility view."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.types import RelationType
from sqlbuild.adapter.type_system.main.normalize_relation_type import normalize_relation_type

_VIEW_PRIVILEGES: frozenset[str] = frozenset({"SELECT", "REFERENCES"})
_GRANTEE_KEYWORDS: dict[str, str] = {"ROLE": "ROLE", "DATABASE_ROLE": "DATABASE ROLE"}
_PRIVILEGE_COLUMN: int = 1
_GRANTED_TO_COLUMN: int = 4
_GRANTEE_COLUMN: int = 5
_GRANT_OPTION_COLUMN: int = 6
_GRANT_OPTION_CLAUSES: dict[str, str] = {"true": " WITH GRANT OPTION"}
_OBJECT_KEYWORDS: dict[RelationType, str] = {RelationType.VIEW: "VIEW"}


def render_snowflake_view_grants(
    *, rows: list[tuple[Any, ...]], destination: str
) -> tuple[str, ...]:
    """Replay SHOW GRANTS rows that apply to a view, skipping OWNERSHIP and shares."""

    statements: list[str] = []
    row: tuple[Any, ...]
    for row in rows:
        privilege: str = str(row[_PRIVILEGE_COLUMN]).upper()
        keyword: str | None = _GRANTEE_KEYWORDS.get(str(row[_GRANTED_TO_COLUMN]).upper())
        if privilege not in _VIEW_PRIVILEGES or keyword is None:
            continue
        grantee: str = ".".join(
            '"' + part.replace('"', '""') + '"' for part in str(row[_GRANTEE_COLUMN]).split(".")
        )
        option: str = _GRANT_OPTION_CLAUSES.get(str(row[_GRANT_OPTION_COLUMN]).lower(), "")
        statements.append(f"GRANT {privilege} ON VIEW {destination} TO {keyword} {grantee}{option}")
    return tuple(statements)


def show_grants_object_kind(relation_type: str) -> str:
    """Return the SHOW GRANTS object keyword for a listed relation type."""

    return _OBJECT_KEYWORDS.get(normalize_relation_type(relation_type), "TABLE")
