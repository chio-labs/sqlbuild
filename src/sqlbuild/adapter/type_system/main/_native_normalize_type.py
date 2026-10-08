"""Native type normalization for the preview compiler engine."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import NormalizedType
from sqlbuild.adapter.contract.types import TypeDialect


def normalize_native_type(
    *, type_sql: str, dialect: TypeDialect | str | None
) -> NormalizedType | None:
    """Return the native normalization, or None where Python must normalize the type."""

    return None
