"""Public adapter type normalization operation."""

from sqlbuild.adapter.contract.models import NormalizedType
from sqlbuild.adapter.contract.types import TypeDialect
from sqlbuild.adapter.type_system._helpers.type_normalization import (
    normalize_type as _normalize_type,
)


def normalize_type(*, type_sql: str, dialect: TypeDialect | str | None) -> NormalizedType:
    """Normalize one warehouse type string into a semantic comparison shape."""

    return _normalize_type(type_sql=type_sql, dialect=dialect)
