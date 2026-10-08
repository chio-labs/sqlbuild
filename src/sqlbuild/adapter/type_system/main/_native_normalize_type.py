"""Native type normalization for the preview compiler engine."""

from __future__ import annotations

import logging

import sqlbuild._native as _native
from sqlbuild.adapter.contract.models import NormalizedType
from sqlbuild.adapter.contract.types import TypeDialect, TypeFamily
from sqlbuild.adapter.type_system.constants import (
    TYPE_NORMALIZATION_LOGGER_NAME,
    TYPE_PARSE_FALLBACK_MESSAGE,
)
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event


def normalize_native_type(
    *, type_sql: str, dialect: TypeDialect | str | None
) -> NormalizedType | None:
    """Return the native normalization, or None where Python must normalize the type."""

    if not isinstance(type_sql, str) or not isinstance(dialect, str | None):
        return None
    native: tuple[tuple[str, str, int | None, int | None, int | None], str | None] | None = (
        _native.normalize_type(type_sql, str(dialect or "generic"))
    )
    if native is None:
        return None
    (normalized_name, family, precision, scale, length), parse_error = native
    if parse_error is not None:
        log_debug_event(
            logger=logging.getLogger(TYPE_NORMALIZATION_LOGGER_NAME),
            message=TYPE_PARSE_FALLBACK_MESSAGE,
            type_sql=type_sql,
            dialect=str(dialect),
            sqlbuild_error=parse_error,
        )
    return NormalizedType(
        normalized_name=normalized_name,
        family=TypeFamily(family),
        precision=precision,
        scale=scale,
        length=length,
    )
