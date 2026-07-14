"""Public adapter numeric family normalization operation."""

from sqlbuild.adapter._helpers.type_normalization import (
    normalize_numeric_family as _normalize_numeric_family,
)
from sqlbuild.adapter.types import TypeDialect


def normalize_numeric_family(*, type_sql: str, dialect: TypeDialect | str | None) -> str | None:
    """Return the normalized numeric family for one type, if numeric."""

    return _normalize_numeric_family(type_sql=type_sql, dialect=dialect)
