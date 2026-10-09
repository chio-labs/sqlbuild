"""Infer expression-source shapes natively, filling the binding catalog's shape cache."""

from __future__ import annotations

import logging
from typing import Any

import sqlbuild._native as _native
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.analysis_session._helpers.deferral_records import record_analysis_deferral
from sqlbuild.compiler.analysis_session._helpers.session_rows import case_sensitive_shapes
from sqlbuild.compiler.analysis_session.constants import (
    DEFERRAL_EXPRESSION_SHAPES,
    DEFERRAL_NO_CATALOG,
    NATIVE_SHAPES_FAILURE_MESSAGE,
)
from sqlbuild.compiler.sql_analysis.constants import NATIVE_DIALECT_ALIASES
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.compile")


def native_expression_source_shapes(
    *, expressions: tuple[str, ...], profile: ExpressionInferenceProfile
) -> tuple[dict[str, str] | None, ...] | None:
    """One shape per expression, or None (recorded) where Python must infer the shapes."""

    catalog: Any = profile.binding_catalog
    if catalog is None:
        record_analysis_deferral(kind=DEFERRAL_NO_CATALOG)
        return None
    cache: dict[str, dict[str, str] | None] = catalog.expression_shapes
    pending: tuple[str, ...] = tuple(
        dict.fromkeys(expression for expression in expressions if expression not in cache)
    )
    inferred: dict[str, dict[str, str] | None] | None = (
        _inferred_shapes(catalog=catalog, pending=pending, profile=profile) if pending else {}
    )
    if inferred is None:
        return None
    cache.update(inferred)
    return tuple(
        None if cache[expression] is None else dict(cache[expression] or {})
        for expression in expressions
    )


def _inferred_shapes(
    *, catalog: Any, pending: tuple[str, ...], profile: ExpressionInferenceProfile
) -> dict[str, dict[str, str] | None] | None:
    dialect: str = profile.sql_analysis_dialect or "generic"
    dialect = NATIVE_DIALECT_ALIASES.get(dialect, dialect)
    shapes, failure = _native.infer_expression_source_shapes(
        catalog.native,
        (
            dialect,
            case_sensitive_shapes(profile=profile, dialect=dialect),
            list(profile.function_return_types.items()),
            list(pending),
        ),
    )
    deferred: int = len(pending) if failure is not None else sum(not done for done, _ in shapes)
    if deferred:
        record_analysis_deferral(kind=DEFERRAL_EXPRESSION_SHAPES, count=deferred)
        log_debug_event(
            logger=_DEBUG_LOGGER, message=NATIVE_SHAPES_FAILURE_MESSAGE, sqlbuild_error=failure
        )
        return None
    return {
        expression: dict(shape) if shape is not None else None
        for expression, (_, shape) in zip(pending, shapes, strict=True)
    }
