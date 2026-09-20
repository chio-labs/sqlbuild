"""Fixture-column inference implementation."""

from __future__ import annotations

from typing import Any, cast

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.analysis.columns import (
    analyze_columns_and_lineage_with_polyglot,
)
from sqlbuild.compiler.compile.constants import (
    POLYGLOT_ARRAY_KIND,
    POLYGLOT_FUNCTION_KIND,
    POLYGLOT_LITERAL_KIND,
    POLYGLOT_STRUCTURED_KINDS,
)
from sqlbuild.compiler.compile.models import (
    FixtureColumnInference,
    InferredColumn,
    PolyglotAnalysisResult,
)
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_KIND_NULL
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql


def infer_fixture_column_facts(
    *, query_sql: str, inference_profile: ExpressionInferenceProfile
) -> FixtureColumnInference | None:
    """Infer fixture columns and identify explicitly untyped NULL projections."""

    analysis: PolyglotAnalysisResult = analyze_columns_and_lineage_with_polyglot(
        query_sql=query_sql,
        inference_profile=inference_profile,
    )
    if not analysis.analysis_succeeded or analysis.has_star or analysis.columns is None:
        return None
    simple_types, null_literal_names, quoted_names = _simple_projection_facts(
        query_sql=query_sql,
        dialect=inference_profile.sql_analysis_dialect,
    )
    return FixtureColumnInference(
        columns=tuple(
            InferredColumn(
                name=column.name,
                type=column.type or simple_types.get(column.name.casefold()),
                nullability=column.nullability,
            )
            for column in analysis.columns
        ),
        null_literal_names=null_literal_names,
        quoted_names=quoted_names,
    )


def _simple_projection_facts(
    *, query_sql: str, dialect: str | None
) -> tuple[dict[str, str], frozenset[str], frozenset[str]]:
    polyglot_sql: Any = import_polyglot_sql()
    try:
        payload: dict[str, Any] = polyglot_sql.parse_one(
            query_sql, dialect=dialect or "generic"
        ).to_dict()
    except polyglot_sql.PolyglotError:
        return {}, frozenset(), frozenset()
    direct_select_payload: object = payload.get("select")
    select_payload: dict[str, Any] | None = _first_select(payload)
    if select_payload is None:
        return {}, frozenset(), frozenset()
    types, null_literal_names, quoted_names = _collect_projection_facts(
        select_payload=select_payload
    )
    effective_null_literal_names: frozenset[str] = (
        null_literal_names if isinstance(direct_select_payload, dict) else frozenset()
    )
    return types, effective_null_literal_names, quoted_names


def _collect_projection_facts(
    *, select_payload: dict[str, Any]
) -> tuple[dict[str, str], frozenset[str], frozenset[str]]:
    types: dict[str, str] = {}
    null_literal_names: set[str] = set()
    quoted_names: set[str] = set()
    for expression in select_payload.get("expressions", []):
        alias_payload: object = expression.get("alias") if isinstance(expression, dict) else None
        if not isinstance(alias_payload, dict):
            continue
        alias: object = alias_payload.get("alias")
        value: object = alias_payload.get("this")
        if not isinstance(alias, dict) or not isinstance(value, dict):
            continue
        name: object = alias.get("name")
        if not isinstance(name, str):
            continue
        if alias.get("quoted") is True:
            quoted_names.add(name.casefold())
        raw_value_kind: object = next(iter(value), "")
        if not isinstance(raw_value_kind, str):
            continue
        value_payload: object = value.get(raw_value_kind)
        if raw_value_kind == POLYGLOT_KIND_NULL:
            null_literal_names.add(name.casefold())
            continue
        inferred_type: str | None = _simple_expression_type(
            value_kind=raw_value_kind,
            value_payload=value_payload,
        )
        if inferred_type is not None:
            types[name.casefold()] = inferred_type
    return types, frozenset(null_literal_names), frozenset(quoted_names)


def _simple_expression_type(*, value_kind: str, value_payload: object) -> str | None:
    if value_kind == POLYGLOT_LITERAL_KIND and isinstance(value_payload, dict):
        value_dict: dict[object, object] = cast(dict[object, object], value_payload)
        return {
            "string": "VARCHAR",
            "number": "NUMBER",
            "boolean": "BOOLEAN",
        }.get(str(value_dict.get("literal_type")))
    if value_kind == POLYGLOT_ARRAY_KIND:
        return "ARRAY"
    if value_kind in POLYGLOT_STRUCTURED_KINDS:
        return "VARIANT"
    if value_kind == POLYGLOT_FUNCTION_KIND and isinstance(value_payload, dict):
        value_dict = cast(dict[object, object], value_payload)
        function_name: str = str(value_dict.get("name") or "").upper()
        return {
            "ARRAY_CONSTRUCT": "ARRAY",
            "OBJECT_CONSTRUCT": "OBJECT",
            "PARSE_JSON": "VARIANT",
        }.get(function_name)
    return None


def _first_select(payload: object) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        payload_dict: dict[object, object] = cast(dict[object, object], payload)
        select_payload: object = payload_dict.get("select")
        if isinstance(select_payload, dict):
            return cast(dict[str, Any], select_payload)
        for value in payload_dict.values():
            found: dict[str, Any] | None = _first_select(value)
            if found is not None:
                return found
    if isinstance(payload, list):
        for value in payload:
            found = _first_select(value)
            if found is not None:
                return found
    return None
