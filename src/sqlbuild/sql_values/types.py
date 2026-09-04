"""Immutable logical values shared by SQLBuild-authored SQL features."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum


class SqlValueKind(StrEnum):
    """Closed logical kinds accepted by the typed SQL value boundary."""

    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    FLOAT = "float"
    DECIMAL = "decimal"
    NULL = "null"
    LIST = "list"
    SET = "set"
    OBJECT = "object"


class CollectionRendering(StrEnum):
    """Physical rendering choices for homogeneous SQL collections."""

    VALUE_LIST = "value_list"
    ARRAY = "array"


class StateSqlValueType(StrEnum):
    """Closed physical value kinds used by warehouse state columns."""

    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    TIMESTAMP = "timestamp"
    TEXT_TIMESTAMP = "text_timestamp"
    DATE = "date"
    JSON = "json"


type SqlScalar = str | int | bool | float | Decimal | None
type SqlValuePayload = SqlScalar | tuple[object, ...]
type SqlCollectionRendering = CollectionRendering
