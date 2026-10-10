"""Infer expression-source shapes natively, filling the binding catalog's shape cache."""

from __future__ import annotations

from typing import Any

import sqlbuild._native as _native
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.adapter.contract.types import FunctionNullabilityRule
from sqlbuild.compiler.analysis_session._helpers.deferral_records import record_analysis_deferral
from sqlbuild.compiler.analysis_session._helpers.profile_rows import (
    adapter_nullability_rules,
    case_sensitive_shapes,
    nullability_rule_rows,
)
from sqlbuild.compiler.analysis_session.constants import ADAPTER_NULLABILITY_CALLBACK
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.compiler.sql_analysis.constants import NATIVE_DIALECT_ALIASES
from sqlbuild.compiler.sql_analysis.main._binding_catalog import create_binding_catalog


def native_expression_source_shapes(
    *, expressions: tuple[str, ...], profile: ExpressionInferenceProfile
) -> tuple[dict[str, str] | None, ...]:
    """One shape per expression; a native internal failure raises `NativeCompilerError`."""

    dialect: str = profile.sql_analysis_dialect or "generic"
    dialect = NATIVE_DIALECT_ALIASES.get(dialect, dialect)
    catalog: Any = profile.binding_catalog or create_binding_catalog(
        dialect=dialect,
        quoted_ignore_case=profile.quoted_identifiers_ignore_case,
        known_functions=(),
        known_types=(),
        relations={},
    )
    cache: dict[str, dict[str, str] | None] = catalog.expression_shapes
    pending: tuple[str, ...] = tuple(
        dict.fromkeys(expression for expression in expressions if expression not in cache)
    )
    if pending:
        adapter_rules: dict[str, FunctionNullabilityRule] = adapter_nullability_rules(profile)
        if adapter_rules:
            record_analysis_deferral(kind=ADAPTER_NULLABILITY_CALLBACK)
        shapes: list[list[tuple[str, str]] | None] = _native.infer_expression_source_shapes(
            catalog.native,
            (
                dialect,
                case_sensitive_shapes(profile=profile, dialect=dialect),
                list(profile.function_return_types.items()),
                nullability_rule_rows(profile),
                list(pending),
            ),
            (adapter_rules, InferredNullability) if adapter_rules else None,
        )
        cache.update(
            (expression, dict(shape) if shape is not None else None)
            for expression, shape in zip(pending, shapes, strict=True)
        )
    return tuple(
        None if cache[expression] is None else dict(cache[expression] or {})
        for expression in expressions
    )
