"""Public fixture-column inference entrypoint."""

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
from sqlbuild.compiler.compile.models import InferredColumn, PolyglotAnalysisResult
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql


def infer_fixture_columns(
    *, query_sql: str, inference_profile: ExpressionInferenceProfile
) -> tuple[InferredColumn, ...] | None:
    """Infer fixture columns and conservative simple-literal types without warehouse access."""

    analysis: PolyglotAnalysisResult = analyze_columns_and_lineage_with_polyglot(
        query_sql=query_sql,
        inference_profile=inference_profile,
    )
    if not analysis.analysis_succeeded or analysis.has_star or analysis.columns is None:
        return None
    simple_types: dict[str, str] = _simple_projection_types(
        query_sql=query_sql,
        dialect=inference_profile.sql_analysis_dialect,
    )
    return tuple(
        InferredColumn(
            name=column.name,
            type=column.type or simple_types.get(column.name.casefold()),
            nullability=column.nullability,
        )
        for column in analysis.columns
    )


def _simple_projection_types(*, query_sql: str, dialect: str | None) -> dict[str, str]:
    polyglot_sql: Any = import_polyglot_sql()
    try:
        payload: dict[str, Any] = polyglot_sql.parse_one(
            query_sql, dialect=dialect or "generic"
        ).to_dict()
    except polyglot_sql.PolyglotError:
        return {}
    select_payload: dict[str, Any] | None = _first_select(payload)
    if select_payload is None:
        return {}
    result: dict[str, str] = {}
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
        raw_value_kind: object = next(iter(value), "")
        if not isinstance(raw_value_kind, str):
            continue
        value_kind: str = raw_value_kind
        value_payload: object = value.get(value_kind)
        inferred_type: str | None = None
        if value_kind == POLYGLOT_LITERAL_KIND and isinstance(value_payload, dict):
            inferred_type = {
                "string": "VARCHAR",
                "number": "NUMBER",
                "boolean": "BOOLEAN",
            }.get(str(value_payload.get("literal_type")))
        elif value_kind == POLYGLOT_ARRAY_KIND:
            inferred_type = "ARRAY"
        elif value_kind in POLYGLOT_STRUCTURED_KINDS:
            inferred_type = "VARIANT"
        elif value_kind == POLYGLOT_FUNCTION_KIND and isinstance(value_payload, dict):
            function_name: str = str(value_payload.get("name") or "").upper()
            inferred_type = {
                "ARRAY_CONSTRUCT": "ARRAY",
                "OBJECT_CONSTRUCT": "OBJECT",
                "PARSE_JSON": "VARIANT",
            }.get(function_name)
        if inferred_type is not None:
            result[name.casefold()] = inferred_type
    return result


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
