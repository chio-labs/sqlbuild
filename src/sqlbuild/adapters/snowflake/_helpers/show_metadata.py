"""Map Snowflake SHOW TABLES and SHOW VIEWS rows onto INFORMATION_SCHEMA relation semantics."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.adapter.relations.main.relation_age_timestamp import relation_age_timestamp_utc
from sqlbuild.adapter.relations.models import ListedRelation

_MISSING_OBJECT_ERRNO: int = 2003
_MISSING_OBJECT_MESSAGE: str = "does not exist or not authorized"
_TRUE_FLAGS: frozenset[str] = frozenset({"Y", "YES", "TRUE"})
_MISSING_SCHEMA_MARKER: str = "schema '"
_MISSING_DATABASE_MARKER: str = "database '"
_TRANSIENT_KIND: str = "TRANSIENT"
_TEMPORARY_KIND: str = "TEMPORARY"


def listed_relation_from_show_table(
    *, row: Mapping[str, object], database: str | None
) -> ListedRelation:
    """Translate one SHOW TABLES row into the relation INFORMATION_SCHEMA.TABLES would list."""

    kind: str = str(row.get("kind") or "").upper()
    relation_type: str = "base table"
    if _flag(row.get("is_external")):
        relation_type = "external table"
    elif kind == _TEMPORARY_KIND:
        relation_type = "temporary table"
    elif _flag(row.get("is_event")):
        relation_type = "event table"
    return _listed_relation(
        row=row,
        database=database,
        relation_type=relation_type,
        is_transient=kind == _TRANSIENT_KIND,
        retention_days=_retention_days(row.get("retention_time")),
    )


def listed_relation_from_show_view(
    *, row: Mapping[str, object], database: str | None
) -> ListedRelation:
    """Translate one SHOW VIEWS row into the relation INFORMATION_SCHEMA.TABLES would list."""

    return _listed_relation(
        row=row,
        database=database,
        relation_type="materialized view" if _flag(row.get("is_materialized")) else "view",
        is_transient=None,
        retention_days=None,
    )


def is_missing_object_error(error: Exception) -> bool:
    """Return whether SHOW failed because the schema is absent or invisible to the role."""

    return (
        getattr(error, "errno", None) == _MISSING_OBJECT_ERRNO
        or _MISSING_OBJECT_MESSAGE in str(error).lower()
    )


def is_missing_schema_error(error: Exception) -> bool:
    """Return whether SHOW failed for a missing schema; a missing database is a real failure."""

    message: str = str(error).lower()
    return (
        is_missing_object_error(error)
        and _MISSING_SCHEMA_MARKER in message
        and _MISSING_DATABASE_MARKER not in message
    )


def _listed_relation(
    *,
    row: Mapping[str, object],
    database: str | None,
    relation_type: str,
    is_transient: bool | None,
    retention_days: int | None,
) -> ListedRelation:
    stored_name: str = str(row["name"])
    return ListedRelation(
        stored_name=stored_name,
        relation=RelationInfo(
            database=database,
            schema=str(row["schema_name"]).lower(),
            name=stored_name.lower(),
            relation_type=relation_type,
            is_transient=is_transient,
            created_at=relation_age_timestamp_utc(row.get("created_on")),
            last_altered_at=None,
            retention_days=retention_days,
        ),
    )


def _flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().upper() in _TRUE_FLAGS


def _retention_days(value: object) -> int | None:
    text: str = str(value if value is not None else "").strip()
    return int(text) if text.lstrip("-").isdigit() else None
