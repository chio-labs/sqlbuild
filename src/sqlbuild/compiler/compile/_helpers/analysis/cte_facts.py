"""Conservative CTE output fact recovery for SQL analysis."""

from __future__ import annotations

from typing import Any, Protocol, cast

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.adapter.contract.types import TypeFamily
from sqlbuild.adapter.type_system.main.normalize_type import normalize_type
from sqlbuild.adapter.type_system.main.types_equal import types_equal
from sqlbuild.compiler.compile.constants import SQL_WILDCARD_TOKEN
from sqlbuild.compiler.compile.models import CteFactResolvers, NonNullFilterContext
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_COLUMN_USES as _POLYGLOT_ANALYSIS_COLUMN_USES,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_CONTEXT as _POLYGLOT_ANALYSIS_CONTEXT,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_CONTEXT_FILTER as _POLYGLOT_ANALYSIS_CONTEXT_FILTER,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_EXPRESSION_SQL as _POLYGLOT_ANALYSIS_EXPRESSION_SQL,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_BINARY_OPERAND_COUNT as _POLYGLOT_BINARY_OPERAND_COUNT,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_BOOLEAN_RESULT_KINDS as _POLYGLOT_BOOLEAN_RESULT_KINDS,
)
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_KIND_ALIAS as _POLYGLOT_KIND_ALIAS
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_KIND_AND as _POLYGLOT_KIND_AND
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_ANNOTATED as _POLYGLOT_KIND_ANNOTATED,
)
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_KIND_CASE as _POLYGLOT_KIND_CASE
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_KIND_CAST as _POLYGLOT_KIND_CAST
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_COALESCE as _POLYGLOT_KIND_COALESCE,
)
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_KIND_COLUMN as _POLYGLOT_KIND_COLUMN
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_KIND_CONCAT as _POLYGLOT_KIND_CONCAT
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_FUNCTION as _POLYGLOT_KIND_FUNCTION,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_IF_FUNC as _POLYGLOT_KIND_IF_FUNC,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_IS_NULL as _POLYGLOT_KIND_IS_NULL,
)
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_KIND_LITERAL as _POLYGLOT_KIND_LITERAL
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_KIND_NULL as _POLYGLOT_KIND_NULL
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_KIND_PAREN as _POLYGLOT_KIND_PAREN
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_KIND_SELECT as _POLYGLOT_KIND_SELECT
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_SUBSTRING as _POLYGLOT_KIND_SUBSTRING,
)
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_KIND_TABLE as _POLYGLOT_KIND_TABLE
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_LITERAL_TYPE_STRING as _POLYGLOT_LITERAL_TYPE_STRING,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_NULLIF_FUNCTION_NAME as _POLYGLOT_NULLIF_FUNCTION_NAME,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_COLUMN as _POLYGLOT_PAYLOAD_COLUMN,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_LEFT as _POLYGLOT_PAYLOAD_LEFT,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_LITERAL_TYPE as _POLYGLOT_PAYLOAD_LITERAL_TYPE,
)
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_PAYLOAD_NAME as _POLYGLOT_PAYLOAD_NAME
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_NOT as _POLYGLOT_PAYLOAD_NOT,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_RIGHT as _POLYGLOT_PAYLOAD_RIGHT,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_TABLE as _POLYGLOT_PAYLOAD_TABLE,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_THIS as _POLYGLOT_PAYLOAD_THIS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_WHERE_CLAUSE as _POLYGLOT_PAYLOAD_WHERE_CLAUSE,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_SET_OPERATION_KINDS as _POLYGLOT_SET_OPERATION_KINDS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_TYPE_PASSTHROUGH_KINDS as _POLYGLOT_TYPE_PASSTHROUGH_KINDS,
)
from sqlbuild.compiler.sql_analysis.constants import SQL_NULL_KEYWORD as _SQL_NULL_KEYWORD

_NULL_SET_OPERATION_TYPE: str = "__SQLBUILD_NULL_SET_OPERATION_TYPE__"


class _ExpressionTypeResolver(Protocol):
    def __call__(
        self, *, expression: Any, inference_profile: ExpressionInferenceProfile
    ) -> str | None: ...


class _NullabilityResolver(Protocol):
    def __call__(
        self,
        *,
        expression: Any,
        alias_nullability: dict[str, InferredNullability],
        column_nullability_by_table: dict[str, dict[str, InferredNullability]],
        inference_profile: ExpressionInferenceProfile,
    ) -> InferredNullability: ...


class _ShallowNullabilityResolver(Protocol):
    def __call__(
        self, *, expression: Any, inference_profile: ExpressionInferenceProfile
    ) -> InferredNullability: ...


class _AliasNullabilityResolver(Protocol):
    def __call__(
        self,
        *,
        select: Any,
        column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    ) -> dict[str, InferredNullability]: ...


def _polyglot_cte_passthrough_facts(
    *,
    polyglot_module: Any,
    cleaned_sql: str,
    dialect: str | None,
    column_types_by_table: dict[str, dict[str, str]],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    inference_profile: ExpressionInferenceProfile,
    analysis: dict[str, Any],
    resolvers: CteFactResolvers,
) -> tuple[dict[str, str], dict[str, InferredNullability], frozenset[str], Any | None]:
    """Recover facts that compact analysis skips across direct CTE reads."""

    if not analysis.get("cteFacts") or not (column_types_by_table or column_nullability_by_table):
        return {}, {}, frozenset(), None
    try:
        parsed: Any = polyglot_module.parse_one(cleaned_sql, dialect=dialect or "generic")
    except polyglot_module.PolyglotError:
        return {}, {}, frozenset(), None
    ctes: tuple[tuple[str, Any, bool], ...] = _polyglot_top_level_ctes(parsed)
    if not ctes:
        return {}, {}, frozenset(), parsed
    inferred_types: dict[str, str] = (
        _polyglot_cte_passthrough_types_from_parsed(
            parsed=parsed,
            column_types_by_table=column_types_by_table,
            inference_profile=inference_profile,
            expression_type_resolver=resolvers.expression_type,
        )
        if column_types_by_table
        else {}
    )
    inferred_nullability: dict[str, InferredNullability] = (
        _polyglot_cte_passthrough_nullability_from_parsed(
            parsed=parsed,
            column_nullability_by_table=column_nullability_by_table,
            inference_profile=inference_profile,
            nullability_resolver=resolvers.nullability,
            shallow_nullability_resolver=resolvers.shallow_nullability,
            alias_nullability_resolver=resolvers.alias_nullability,
        )
        if column_nullability_by_table
        else {}
    )
    return (
        inferred_types,
        inferred_nullability,
        _polyglot_direct_cte_output_names(
            parsed=parsed,
            cte_names=frozenset(name for name, _, _ in ctes),
        ),
        parsed,
    )


def _polyglot_direct_cte_output_names(*, parsed: Any, cte_names: frozenset[str]) -> frozenset[str]:
    normalized_cte_names: frozenset[str] = frozenset(name.casefold() for name in cte_names)
    terminal_tables: tuple[Any, ...] = _polyglot_direct_select_tables(parsed)
    if not any(
        str(getattr(table, "name", "") or "").casefold() in normalized_cte_names
        for table in terminal_tables
    ):
        return frozenset()
    output_names: set[str] = set()
    projection: Any
    for projection in getattr(parsed, "expressions", ()):
        projection = _unwrap_polyglot_annotations(projection)
        expression: Any = (
            projection.this
            if str(getattr(projection, "kind", "")) == _POLYGLOT_KIND_ALIAS
            else projection
        )
        if str(getattr(expression, "kind", "")) != _POLYGLOT_KIND_COLUMN:
            continue
        output_name: str = str(getattr(projection, "output_name", "") or "")
        if output_name and output_name != SQL_WILDCARD_TOKEN:
            output_names.add(output_name)
    return frozenset(output_names)


def _polyglot_cte_passthrough_types_from_parsed(
    *,
    parsed: Any,
    column_types_by_table: dict[str, dict[str, str]],
    inference_profile: ExpressionInferenceProfile,
    expression_type_resolver: _ExpressionTypeResolver,
    top_level_ctes: tuple[tuple[str, Any, bool], ...] | None = None,
    referenced_table_names: tuple[str, ...] | None = None,
) -> dict[str, str]:
    ctes: tuple[tuple[str, Any, bool], ...] = (
        _polyglot_top_level_ctes(parsed) if top_level_ctes is None else top_level_ctes
    )
    if not ctes:
        return {}
    relation_types: dict[str, dict[str, str]] = _polyglot_referenced_relation_facts(
        parsed=parsed,
        facts_by_table=column_types_by_table,
        table_names=referenced_table_names,
    )
    cte_name: str
    cte_body: Any
    for cte_name, cte_body, has_column_aliases in ctes:
        if has_column_aliases:
            continue
        inferred: dict[str, str] = _polyglot_select_output_types(
            select=cte_body,
            relation_types=relation_types,
            inference_profile=inference_profile,
            expression_type_resolver=expression_type_resolver,
        )
        if inferred:
            relation_types[cte_name] = inferred
    if str(getattr(parsed, "kind", "")) in _POLYGLOT_SET_OPERATION_KINDS:
        return _polyglot_set_operation_output_types(
            operation=parsed,
            relation_types=relation_types,
            inference_profile=inference_profile,
            expression_type_resolver=expression_type_resolver,
        )
    return _polyglot_direct_select_output_types(
        select=parsed,
        relation_types=relation_types,
        inference_profile=inference_profile,
        expression_type_resolver=expression_type_resolver,
    )


def _polyglot_cte_passthrough_nullability_from_parsed(
    *,
    parsed: Any,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    inference_profile: ExpressionInferenceProfile,
    nullability_resolver: _NullabilityResolver,
    shallow_nullability_resolver: _ShallowNullabilityResolver,
    alias_nullability_resolver: _AliasNullabilityResolver,
    top_level_ctes: tuple[tuple[str, Any, bool], ...] | None = None,
    referenced_table_names: tuple[str, ...] | None = None,
) -> dict[str, InferredNullability]:
    ctes: tuple[tuple[str, Any, bool], ...] = (
        _polyglot_top_level_ctes(parsed) if top_level_ctes is None else top_level_ctes
    )
    if not ctes:
        return {}
    relation_nullability: dict[str, dict[str, InferredNullability]] = (
        _polyglot_referenced_relation_facts(
            parsed=parsed,
            facts_by_table=column_nullability_by_table,
            table_names=referenced_table_names,
        )
    )
    for cte_name, cte_body, has_column_aliases in ctes:
        if has_column_aliases:
            continue
        inferred: dict[str, InferredNullability] = _polyglot_direct_select_output_nullability(
            select=cte_body,
            relation_nullability=relation_nullability,
            inference_profile=inference_profile,
            nullability_resolver=nullability_resolver,
            shallow_nullability_resolver=shallow_nullability_resolver,
            alias_nullability_resolver=alias_nullability_resolver,
        )
        if inferred:
            relation_nullability[cte_name] = inferred
    return _polyglot_direct_select_output_nullability(
        select=parsed,
        relation_nullability=relation_nullability,
        inference_profile=inference_profile,
        nullability_resolver=nullability_resolver,
        shallow_nullability_resolver=shallow_nullability_resolver,
        alias_nullability_resolver=alias_nullability_resolver,
    )


def _polyglot_referenced_relation_facts[T](
    *,
    parsed: Any,
    facts_by_table: dict[str, dict[str, T]],
    table_names: tuple[str, ...] | None = None,
) -> dict[str, dict[str, T]]:
    referenced_facts: dict[str, dict[str, T]] = {}
    names: tuple[str, ...] = (
        tuple(
            str(getattr(table, "name", "") or "") for table in parsed.find_all(_POLYGLOT_KIND_TABLE)
        )
        if table_names is None
        else table_names
    )
    for table_name in names:
        column_facts: dict[str, T] | None = facts_by_table.get(table_name)
        if column_facts is not None:
            referenced_facts[table_name] = column_facts
    return referenced_facts


def _polyglot_direct_select_output_nullability(
    *,
    select: Any,
    relation_nullability: dict[str, dict[str, InferredNullability]],
    inference_profile: ExpressionInferenceProfile,
    nullability_resolver: _NullabilityResolver,
    shallow_nullability_resolver: _ShallowNullabilityResolver,
    alias_nullability_resolver: _AliasNullabilityResolver,
) -> dict[str, InferredNullability]:
    if str(getattr(select, "kind", "")) != _POLYGLOT_KIND_SELECT:
        return {}
    direct_table_names: tuple[str, ...] = tuple(
        str(getattr(table, "name", "") or "") for table in _polyglot_direct_select_tables(select)
    )
    scoped_nullability: dict[str, dict[str, InferredNullability]] = {}
    for table_name in direct_table_names:
        column_facts: dict[str, InferredNullability] | None = _case_insensitive_mapping_get(
            mapping=relation_nullability,
            key=table_name,
        )
        if column_facts is not None:
            scoped_nullability[table_name] = dict(column_facts)
    has_known_nullability: bool = _has_known_nullability(scoped_nullability)
    alias_nullability: dict[str, InferredNullability] = (
        alias_nullability_resolver(
            select=select,
            column_nullability_by_table=scoped_nullability,
        )
        if has_known_nullability
        else {}
    )
    non_null_filter_context: NonNullFilterContext | None = _polyglot_non_null_filter_context(
        select=select,
        column_nullability_by_table=scoped_nullability,
    )
    inferred: dict[str, InferredNullability] = {}
    projection: Any
    for raw_projection in getattr(select, "expressions", ()):
        projection: Any = _unwrap_polyglot_annotations(raw_projection)
        if bool(getattr(projection, "is_star", False)):
            continue
        output_name: str = str(getattr(projection, "output_name", "") or "")
        if not output_name or output_name == SQL_WILDCARD_TOKEN:
            continue
        expression: Any = (
            projection.this
            if str(getattr(projection, "kind", "")) == _POLYGLOT_KIND_ALIAS
            else projection
        )
        nullability: InferredNullability = (
            InferredNullability.NON_NULL
            if _polyglot_expression_is_non_null_after_filter(
                expression=expression,
                context=non_null_filter_context,
            )
            else (
                nullability_resolver(
                    expression=expression,
                    alias_nullability=alias_nullability,
                    column_nullability_by_table=scoped_nullability,
                    inference_profile=inference_profile,
                )
                if has_known_nullability
                else shallow_nullability_resolver(
                    expression=expression,
                    inference_profile=inference_profile,
                )
            )
        )
        if nullability != InferredNullability.UNKNOWN:
            inferred[output_name] = nullability
    return inferred


def _polyglot_filtered_non_null_outputs(
    *,
    polyglot_module: Any,
    cleaned_sql: str,
    dialect: str | None,
    analysis: dict[str, Any],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    parsed: Any | None = None,
) -> frozenset[str]:
    column_uses: object = analysis.get(_POLYGLOT_ANALYSIS_COLUMN_USES)
    if not isinstance(column_uses, list) or not any(
        isinstance(value, dict)
        and value.get(_POLYGLOT_ANALYSIS_CONTEXT) == _POLYGLOT_ANALYSIS_CONTEXT_FILTER
        and _SQL_NULL_KEYWORD in str(value.get(_POLYGLOT_ANALYSIS_EXPRESSION_SQL) or "").upper()
        for value in column_uses
    ):
        return frozenset()
    if parsed is None:
        try:
            parsed = polyglot_module.parse_one(
                cleaned_sql,
                dialect=dialect or "generic",
            )
        except polyglot_module.PolyglotError:
            return frozenset()
    select: Any | None = parsed
    if str(getattr(select, "kind", "")) != _POLYGLOT_KIND_SELECT:
        select = parsed.find(_POLYGLOT_KIND_SELECT)
    if select is None or str(getattr(select, "kind", "")) != _POLYGLOT_KIND_SELECT:
        return frozenset()
    outputs: set[str] = set()
    context: NonNullFilterContext | None = _polyglot_non_null_filter_context(
        select=select,
        column_nullability_by_table=column_nullability_by_table,
    )
    for raw_projection in getattr(select, "expressions", ()):
        projection: Any = _unwrap_polyglot_annotations(raw_projection)
        output_name: str = str(getattr(projection, "output_name", "") or "")
        if not output_name or output_name == SQL_WILDCARD_TOKEN:
            continue
        expression: Any = (
            projection.this
            if str(getattr(projection, "kind", "")) == _POLYGLOT_KIND_ALIAS
            else projection
        )
        if _polyglot_expression_is_non_null_after_filter(
            expression=expression,
            context=context,
        ):
            outputs.add(output_name)
    return frozenset(outputs)


def _polyglot_expression_is_non_null_after_filter(
    *,
    expression: Any,
    context: NonNullFilterContext | None,
) -> bool:
    if context is None:
        return False
    expression_reference: tuple[str, str] | None = _polyglot_direct_column_reference(expression)
    if expression_reference is None:
        return False
    resolved_expression: tuple[str, str] | None = _polyglot_resolved_relation_column(
        reference=expression_reference,
        relations=context.relations,
    )
    return resolved_expression is not None and resolved_expression in context.columns


def _polyglot_non_null_filter_context(
    *,
    select: Any,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
) -> NonNullFilterContext | None:
    where_payload: object = select.arg(_POLYGLOT_PAYLOAD_WHERE_CLAUSE)
    if not isinstance(where_payload, dict):
        return None
    predicate: object = cast(dict[str, object], where_payload).get(_POLYGLOT_PAYLOAD_THIS)
    non_null_references: tuple[tuple[str, str], ...] = _polyglot_non_null_conjuncts(predicate)
    if not non_null_references:
        return None
    relations: list[tuple[str, dict[str, InferredNullability]]] = []
    for table in _polyglot_direct_select_tables(select):
        table_name: str = str(getattr(table, "name", "") or "")
        alias: str = str(getattr(table, "alias_or_name", "") or "")
        columns: dict[str, InferredNullability] | None = _case_insensitive_mapping_get(
            mapping=column_nullability_by_table,
            key=table_name,
        )
        if columns is not None:
            relations.append((alias or table_name, columns))
    relation_tuple: tuple[tuple[str, dict[str, InferredNullability]], ...] = tuple(relations)
    columns: frozenset[tuple[str, str]] = frozenset(
        resolved
        for reference in non_null_references
        if (
            resolved := _polyglot_resolved_relation_column(
                reference=reference,
                relations=relation_tuple,
            )
        )
    )
    return NonNullFilterContext(relations=relation_tuple, columns=columns) if columns else None


def _polyglot_direct_column_reference(expression: Any) -> tuple[str, str] | None:
    expression = _unwrap_polyglot_annotations(expression)
    if str(getattr(expression, "kind", "")) == _POLYGLOT_KIND_CAST:
        expression = _unwrap_polyglot_annotations(getattr(expression, "this", None))
    if str(getattr(expression, "kind", "")) != _POLYGLOT_KIND_COLUMN:
        return None
    column_name: str = str(getattr(expression, "name", "") or "")
    if not column_name:
        return None
    expression_args: object = getattr(expression, "args", None)
    table_name: str = ""
    if isinstance(expression_args, dict):
        table_name = _polyglot_name_payload_value(
            cast(dict[str, object], expression_args).get(_POLYGLOT_PAYLOAD_TABLE)
        )
    return table_name, column_name


def _polyglot_resolved_relation_column(
    *,
    reference: tuple[str, str],
    relations: tuple[tuple[str, dict[str, InferredNullability]], ...],
) -> tuple[str, str] | None:
    table_name, column_name = reference
    matching: list[tuple[str, str]] = []
    for alias, columns in relations:
        if table_name and alias.casefold() != table_name.casefold():
            continue
        column_key: str | None = _case_insensitive_mapping_key(
            mapping=columns,
            key=column_name,
        )
        if column_key is not None:
            matching.append((alias.casefold(), column_key.casefold()))
    return matching[0] if len(matching) == 1 else None


def _polyglot_non_null_conjuncts(payload: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(payload, dict):
        return ()
    payload_dict: dict[str, object] = cast(dict[str, object], payload)
    paren_payload: object = payload_dict.get(_POLYGLOT_KIND_PAREN)
    if isinstance(paren_payload, dict):
        paren_payload_dict: dict[str, object] = cast(dict[str, object], paren_payload)
        return _polyglot_non_null_conjuncts(paren_payload_dict.get(_POLYGLOT_PAYLOAD_THIS))
    and_payload: object = payload_dict.get(_POLYGLOT_KIND_AND)
    if isinstance(and_payload, dict):
        and_payload_dict: dict[str, object] = cast(dict[str, object], and_payload)
        return (
            *_polyglot_non_null_conjuncts(and_payload_dict.get(_POLYGLOT_PAYLOAD_LEFT)),
            *_polyglot_non_null_conjuncts(and_payload_dict.get(_POLYGLOT_PAYLOAD_RIGHT)),
        )
    is_null_payload: object = payload_dict.get(_POLYGLOT_KIND_IS_NULL)
    is_null_payload_dict: dict[str, object] = (
        cast(dict[str, object], is_null_payload) if isinstance(is_null_payload, dict) else {}
    )
    if not is_null_payload_dict or is_null_payload_dict.get(_POLYGLOT_PAYLOAD_NOT) is not True:
        return ()
    expression_payload: object = is_null_payload_dict.get(_POLYGLOT_PAYLOAD_THIS)
    if not isinstance(expression_payload, dict):
        return ()
    expression_payload_dict: dict[str, object] = cast(dict[str, object], expression_payload)
    column_payload: object = expression_payload_dict.get(_POLYGLOT_PAYLOAD_COLUMN)
    if not isinstance(column_payload, dict):
        return ()
    column_payload_dict: dict[str, object] = cast(dict[str, object], column_payload)
    column_name: str = _polyglot_name_payload_value(column_payload_dict.get(_POLYGLOT_PAYLOAD_NAME))
    table_name: str = _polyglot_name_payload_value(column_payload_dict.get(_POLYGLOT_PAYLOAD_TABLE))
    return ((table_name, column_name),) if column_name else ()


def _polyglot_star_output_types(
    *, projection: Any, types_by_alias: dict[str, dict[str, str]]
) -> dict[str, str]:
    if getattr(projection, "args", {}).get("rename"):
        return {}
    table_payload: object = getattr(projection, "args", {}).get("table")
    table_name: str = _polyglot_name_payload_value(table_payload)
    source_types: list[dict[str, str]] = []
    if table_name:
        column_types: dict[str, str] | None = _case_insensitive_mapping_get(
            mapping=types_by_alias,
            key=table_name,
        )
        if column_types is not None:
            source_types.append(column_types)
    else:
        seen_relations: set[int] = set()
        for column_types in types_by_alias.values():
            if id(column_types) in seen_relations:
                continue
            seen_relations.add(id(column_types))
            source_types.append(column_types)
    excluded_names: frozenset[str] = frozenset(
        name.casefold()
        for value in (getattr(projection, "args", {}).get("except") or ())
        if (name := _polyglot_name_payload_value(value))
    )
    replaced_names: frozenset[str] = frozenset(
        name.casefold()
        for value in (getattr(projection, "args", {}).get("replace") or ())
        if isinstance(value, dict)
        and (name := _polyglot_name_payload_value(cast(dict[str, object], value).get("alias")))
    )
    inferred: dict[str, str] = {}
    ambiguous_names: set[str] = set()
    for column_types in source_types:
        for column_name, column_type in column_types.items():
            normalized_name: str = column_name.casefold()
            if normalized_name in excluded_names or normalized_name in replaced_names:
                continue
            existing_name: str | None = next(
                (name for name in inferred if name.casefold() == normalized_name),
                None,
            )
            if existing_name is not None:
                ambiguous_names.add(existing_name)
                continue
            inferred[column_name] = column_type
    for ambiguous_name in ambiguous_names:
        inferred.pop(ambiguous_name, None)
    return inferred


def _polyglot_top_level_ctes(root: Any) -> tuple[tuple[str, Any, bool], ...]:
    targeted_ctes: object = getattr(root, "with_ctes", None)
    if callable(targeted_ctes):
        values: object = targeted_ctes()
        if isinstance(values, list):
            return tuple(
                (str(name), body, bool(has_column_alias)) for name, has_column_alias, body in values
            )
    with_payload: object = root.arg("with")
    raw_ctes: object = (
        cast(dict[str, object], with_payload).get("ctes")
        if isinstance(with_payload, dict)
        else None
    )
    if not isinstance(raw_ctes, list):
        return ()
    children: tuple[Any, ...] = tuple(root.children())
    if len(children) < len(raw_ctes):
        return ()
    cte_bodies: tuple[Any, ...] = children[-len(raw_ctes) :]
    ctes: list[tuple[str, Any, bool]] = []
    for raw_cte, body in zip(raw_ctes, cte_bodies, strict=True):
        if not isinstance(raw_cte, dict):
            return ()
        cte_payload: dict[str, object] = cast(dict[str, object], raw_cte)
        cte_name: str = _polyglot_name_payload_value(cte_payload.get("alias"))
        if not cte_name:
            return ()
        columns: object = cte_payload.get("columns")
        ctes.append((cte_name, body, isinstance(columns, list) and bool(columns)))
    return tuple(ctes)


def _polyglot_select_output_types(
    *,
    select: Any,
    relation_types: dict[str, dict[str, str]],
    inference_profile: ExpressionInferenceProfile,
    expression_type_resolver: _ExpressionTypeResolver,
) -> dict[str, str]:
    select = _unwrap_polyglot_annotations(select)
    if _polyglot_top_level_ctes(select):
        return _polyglot_cte_passthrough_types_from_parsed(
            parsed=select,
            column_types_by_table=relation_types,
            inference_profile=inference_profile,
            expression_type_resolver=expression_type_resolver,
        )
    if str(getattr(select, "kind", "")) in _POLYGLOT_SET_OPERATION_KINDS:
        return _polyglot_set_operation_output_types(
            operation=select,
            relation_types=relation_types,
            inference_profile=inference_profile,
            expression_type_resolver=expression_type_resolver,
        )
    return _polyglot_direct_select_output_types(
        select=select,
        relation_types=relation_types,
        inference_profile=inference_profile,
        expression_type_resolver=expression_type_resolver,
    )


def _polyglot_set_operation_output_types(
    *,
    operation: Any,
    relation_types: dict[str, dict[str, str]],
    inference_profile: ExpressionInferenceProfile,
    expression_type_resolver: _ExpressionTypeResolver,
) -> dict[str, str]:
    if bool(operation.arg("by_name")):
        branch_types: list[dict[str, str]] = []
        for side in ("left", "right"):
            branch: Any = operation.arg(side)
            if branch is None:
                return {}
            branch_types.append(
                _polyglot_select_output_types(
                    select=branch,
                    relation_types=relation_types,
                    inference_profile=inference_profile,
                    expression_type_resolver=expression_type_resolver,
                )
            )
        left_types, right_types = branch_types
        return {
            name: common_type
            for name, left_type in left_types.items()
            if (
                common_type := _polyglot_common_set_operation_type(
                    left=left_type,
                    right=_case_insensitive_mapping_get(mapping=right_types, key=name),
                    inference_profile=inference_profile,
                )
            )
            is not None
        }
    branch_slots: list[tuple[tuple[str, str | None], ...]] = []
    for side in ("left", "right"):
        branch: Any = operation.arg(side)
        if branch is None:
            return {}
        inferred: tuple[tuple[str, str | None], ...] = _polyglot_select_output_type_slots(
            select=branch,
            relation_types=relation_types,
            inference_profile=inference_profile,
            expression_type_resolver=expression_type_resolver,
        )
        if not inferred:
            return {}
        branch_slots.append(inferred)
    left_slots, right_slots = branch_slots
    if len(left_slots) != len(right_slots):
        return {}
    return {
        left_name: common_type
        for (left_name, left_type), (_, right_type) in zip(
            left_slots,
            right_slots,
            strict=True,
        )
        if (
            common_type := _polyglot_common_set_operation_type(
                left=left_type,
                right=right_type,
                inference_profile=inference_profile,
            )
        )
        is not None
    }


def _polyglot_select_output_type_slots(
    *,
    select: Any,
    relation_types: dict[str, dict[str, str]],
    inference_profile: ExpressionInferenceProfile,
    expression_type_resolver: _ExpressionTypeResolver,
) -> tuple[tuple[str, str | None], ...]:
    select = _unwrap_polyglot_annotations(select)
    if str(getattr(select, "kind", "")) in _POLYGLOT_SET_OPERATION_KINDS:
        branch_slots: list[tuple[tuple[str, str | None], ...]] = []
        for side in ("left", "right"):
            branch: Any = select.arg(side)
            if branch is None:
                return ()
            slots: tuple[tuple[str, str | None], ...] = _polyglot_select_output_type_slots(
                select=branch,
                relation_types=relation_types,
                inference_profile=inference_profile,
                expression_type_resolver=expression_type_resolver,
            )
            if not slots:
                return ()
            branch_slots.append(slots)
        left_slots, right_slots = branch_slots
        if bool(select.arg("by_name")):
            right_types: dict[str, str | None] = dict(right_slots)
            return tuple(
                (
                    name,
                    _polyglot_common_set_operation_type(
                        left=left_type,
                        right=_case_insensitive_mapping_get(mapping=right_types, key=name),
                        inference_profile=inference_profile,
                    ),
                )
                for name, left_type in left_slots
            )
        if len(left_slots) != len(right_slots):
            return ()
        return tuple(
            (
                left_name,
                _polyglot_common_set_operation_type(
                    left=left_type,
                    right=right_type,
                    inference_profile=inference_profile,
                ),
            )
            for (left_name, left_type), (_, right_type) in zip(
                left_slots,
                right_slots,
                strict=True,
            )
        )
    if str(getattr(select, "kind", "")) != _POLYGLOT_KIND_SELECT:
        return ()
    inferred: dict[str, str] = _polyglot_direct_select_output_types(
        select=select,
        relation_types=relation_types,
        inference_profile=inference_profile,
        expression_type_resolver=expression_type_resolver,
    )
    slots: list[tuple[str, str | None]] = []
    for raw_projection in getattr(select, "expressions", ()):
        projection: Any = _unwrap_polyglot_annotations(raw_projection)
        if bool(getattr(projection, "is_star", False)):
            return ()
        output_name: str = str(getattr(projection, "output_name", "") or "")
        if not output_name or output_name == SQL_WILDCARD_TOKEN:
            return ()
        inferred_type: str | None = _case_insensitive_mapping_get(
            mapping=inferred,
            key=output_name,
        )
        if inferred_type is None:
            expression: Any = (
                projection.this
                if str(getattr(projection, "kind", "")) == _POLYGLOT_KIND_ALIAS
                else projection
            )
            if str(getattr(expression, "kind", "")) == _POLYGLOT_KIND_NULL:
                inferred_type = _NULL_SET_OPERATION_TYPE
        slots.append((output_name, inferred_type))
    return tuple(slots)


def _polyglot_common_set_operation_type(
    *,
    left: str | None,
    right: str | None,
    inference_profile: ExpressionInferenceProfile,
) -> str | None:
    if left == _NULL_SET_OPERATION_TYPE and right == _NULL_SET_OPERATION_TYPE:
        return None
    if left == _NULL_SET_OPERATION_TYPE:
        return right
    if right == _NULL_SET_OPERATION_TYPE:
        return left
    if left is None or right is None:
        return None
    return (
        left
        if _polyglot_types_equal(
            left=left,
            right=right,
            inference_profile=inference_profile,
        )
        else None
    )


def _polyglot_types_equal(
    *,
    left: str,
    right: str,
    inference_profile: ExpressionInferenceProfile,
) -> bool:
    return left == right or types_equal(
        left=left,
        right=right,
        dialect=inference_profile.sql_analysis_dialect,
    )


def _polyglot_direct_select_output_types(
    *,
    select: Any,
    relation_types: dict[str, dict[str, str]],
    inference_profile: ExpressionInferenceProfile,
    expression_type_resolver: _ExpressionTypeResolver,
) -> dict[str, str]:
    if str(getattr(select, "kind", "")) != _POLYGLOT_KIND_SELECT:
        return {}
    types_by_alias: dict[str, dict[str, str]] = {}
    for table in _polyglot_direct_select_tables(select):
        table_name: str = str(getattr(table, "name", "") or "")
        column_types: dict[str, str] | None = _case_insensitive_mapping_get(
            mapping=relation_types,
            key=table_name,
        )
        if column_types is None:
            continue
        types_by_alias[table_name] = column_types
        alias_or_name: str = str(getattr(table, "alias_or_name", "") or "")
        if alias_or_name:
            types_by_alias[alias_or_name] = column_types
    inferred: dict[str, str] = {}
    projection: Any
    for projection in getattr(select, "expressions", ()):
        projection = _unwrap_polyglot_annotations(projection)
        if bool(getattr(projection, "is_star", False)):
            inferred.update(
                _polyglot_star_output_types(
                    projection=projection,
                    types_by_alias=types_by_alias,
                )
            )
            continue
        output_name: str = str(getattr(projection, "output_name", "") or "")
        if not output_name or output_name == SQL_WILDCARD_TOKEN:
            continue
        expression: Any = (
            projection.this
            if str(getattr(projection, "kind", "")) == _POLYGLOT_KIND_ALIAS
            else projection
        )
        inferred_type: str | None = _polyglot_direct_expression_type(
            expression=expression,
            types_by_alias=types_by_alias,
            inference_profile=inference_profile,
            expression_type_resolver=expression_type_resolver,
        )
        if inferred_type is not None:
            inferred[output_name] = inferred_type
    return inferred


def _polyglot_direct_expression_type(
    *,
    expression: Any,
    types_by_alias: dict[str, dict[str, str]],
    inference_profile: ExpressionInferenceProfile,
    expression_type_resolver: _ExpressionTypeResolver,
) -> str | None:
    expression = _unwrap_polyglot_annotations(expression)
    kind: str = str(getattr(expression, "kind", ""))
    inferred_type: str | None = expression_type_resolver(
        expression=expression,
        inference_profile=inference_profile,
    )
    if inferred_type is not None:
        return inferred_type
    if kind == _POLYGLOT_KIND_COLUMN:
        return _polyglot_direct_column_type(
            expression=expression,
            types_by_alias=types_by_alias,
        )
    if kind in _POLYGLOT_BOOLEAN_RESULT_KINDS:
        return "BOOLEAN"
    if kind == _POLYGLOT_KIND_CONCAT:
        operands: tuple[Any, ...] = tuple(
            operand
            for key in ("left", "right")
            if (operand := getattr(expression, "args", {}).get(key)) is not None
        )
        if len(operands) != _POLYGLOT_BINARY_OPERAND_COUNT:
            return None
        operand_types: list[str] = []
        for operand in operands:
            if (
                str(getattr(operand, "kind", "")) == _POLYGLOT_KIND_LITERAL
                and getattr(operand, "args", {}).get(_POLYGLOT_PAYLOAD_LITERAL_TYPE)
                == _POLYGLOT_LITERAL_TYPE_STRING
            ):
                operand_types.append("TEXT")
                continue
            operand_type: str | None = _polyglot_direct_expression_type(
                expression=operand,
                types_by_alias=types_by_alias,
                inference_profile=inference_profile,
                expression_type_resolver=expression_type_resolver,
            )
            if operand_type is None:
                return None
            operand_types.append(operand_type)
        return (
            "TEXT"
            if all(
                normalize_type(
                    type_sql=operand_type,
                    dialect=inference_profile.sql_analysis_dialect,
                ).family
                == TypeFamily.STRING
                for operand_type in operand_types
            )
            else None
        )
    if kind == _POLYGLOT_KIND_SUBSTRING:
        inner: Any | None = getattr(expression, "args", {}).get("this")
        return (
            _polyglot_direct_expression_type(
                expression=inner,
                types_by_alias=types_by_alias,
                inference_profile=inference_profile,
                expression_type_resolver=expression_type_resolver,
            )
            if inner is not None
            else None
        )
    if kind in _POLYGLOT_TYPE_PASSTHROUGH_KINDS:
        inner: Any | None = getattr(expression, "this", None) or getattr(
            expression, "args", {}
        ).get("this")
        return (
            _polyglot_direct_expression_type(
                expression=inner,
                types_by_alias=types_by_alias,
                inference_profile=inference_profile,
                expression_type_resolver=expression_type_resolver,
            )
            if inner is not None
            else None
        )
    result_expressions: tuple[Any, ...] = _polyglot_result_expressions(expression)
    if result_expressions:
        return _polyglot_common_result_type(
            expressions=result_expressions,
            types_by_alias=types_by_alias,
            inference_profile=inference_profile,
            expression_type_resolver=expression_type_resolver,
        )
    return None


def _polyglot_result_expressions(expression: Any) -> tuple[Any, ...]:
    kind: str = str(getattr(expression, "kind", ""))
    args: dict[str, Any] = getattr(expression, "args", {})
    if kind == _POLYGLOT_KIND_COALESCE:
        values: object = args.get("expressions")
        return tuple(values) if isinstance(values, list) else ()
    if kind == _POLYGLOT_KIND_IF_FUNC:
        return tuple(
            value for key in ("true_value", "false_value") if (value := args.get(key)) is not None
        )
    if kind == _POLYGLOT_KIND_CASE:
        values: list[Any] = []
        whens: object = args.get("whens")
        children: tuple[Any, ...] = tuple(expression.children())
        if isinstance(whens, list):
            first_condition_index: int = 1 if args.get("operand") is not None else 0
            values.extend(
                children[first_condition_index + (index * 2) + 1] for index in range(len(whens))
            )
        if args.get("else_") is not None and children:
            values.append(children[-1])
        return tuple(values)
    if (
        kind == _POLYGLOT_KIND_FUNCTION
        and str(getattr(expression, "name", "")).upper() == _POLYGLOT_NULLIF_FUNCTION_NAME
    ):
        values = args.get("args")
        return (values[0],) if isinstance(values, list) and values else ()
    return ()


def _polyglot_common_result_type(
    *,
    expressions: tuple[Any, ...],
    types_by_alias: dict[str, dict[str, str]],
    inference_profile: ExpressionInferenceProfile,
    expression_type_resolver: _ExpressionTypeResolver,
) -> str | None:
    resolved_types: list[str] = []
    for raw_expression in expressions:
        expression: Any = _unwrap_polyglot_annotations(raw_expression)
        if str(getattr(expression, "kind", "")) == _POLYGLOT_KIND_NULL:
            continue
        resolved_type: str | None = _polyglot_direct_expression_type(
            expression=expression,
            types_by_alias=types_by_alias,
            inference_profile=inference_profile,
            expression_type_resolver=expression_type_resolver,
        )
        if resolved_type is None:
            return None
        resolved_types.append(resolved_type)
    if not resolved_types:
        return None
    first_type: str = resolved_types[0]
    if all(
        _polyglot_types_equal(
            left=first_type,
            right=other_type,
            inference_profile=inference_profile,
        )
        for other_type in resolved_types[1:]
    ):
        return first_type
    return None


def _polyglot_direct_select_tables(select: Any) -> tuple[Any, ...]:
    return tuple(
        child
        for child in select.children()
        if str(getattr(child, "kind", "")) == _POLYGLOT_KIND_TABLE
    )


def _polyglot_direct_column_type(
    *, expression: Any, types_by_alias: dict[str, dict[str, str]]
) -> str | None:
    column_name: str = str(getattr(expression, "name", "") or "")
    table_name: str = _polyglot_column_table_name(expression)
    if table_name:
        column_types: dict[str, str] | None = _case_insensitive_mapping_get(
            mapping=types_by_alias,
            key=table_name,
        )
        return (
            _case_insensitive_mapping_get(mapping=column_types, key=column_name)
            if column_types is not None
            else None
        )
    matching_types: list[str] = []
    seen_relations: set[int] = set()
    for column_types in types_by_alias.values():
        if id(column_types) in seen_relations:
            continue
        seen_relations.add(id(column_types))
        inferred_type: str | None = _case_insensitive_mapping_get(
            mapping=column_types,
            key=column_name,
        )
        if inferred_type is not None:
            matching_types.append(inferred_type)
    return matching_types[0] if len(matching_types) == 1 else None


def _case_insensitive_mapping_get[T](*, mapping: dict[str, T], key: str) -> T | None:
    direct: T | None = mapping.get(key)
    if direct is not None:
        return direct
    normalized_key: str = key.casefold()
    matches: list[T] = [
        value for candidate, value in mapping.items() if candidate.casefold() == normalized_key
    ]
    return matches[0] if len(matches) == 1 else None


def _case_insensitive_mapping_key[T](*, mapping: dict[str, T], key: str) -> str | None:
    if key in mapping:
        return key
    normalized_key: str = key.casefold()
    matches: list[str] = [
        candidate for candidate in mapping if candidate.casefold() == normalized_key
    ]
    return matches[0] if len(matches) == 1 else None


def _has_known_nullability(
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
) -> bool:
    for column_facts in column_nullability_by_table.values():
        if any(value != InferredNullability.UNKNOWN for value in column_facts.values()):
            return True
    return False


def _unwrap_polyglot_annotations(expression: Any) -> Any:
    while str(getattr(expression, "kind", "")) == _POLYGLOT_KIND_ANNOTATED:
        expression = expression.this
    return expression


def _polyglot_column_table_name(column: Any) -> str:
    payload: object = column.to_dict().get(_POLYGLOT_PAYLOAD_COLUMN, {})
    if not isinstance(payload, dict):
        return ""
    table_payload: object = payload.get(_POLYGLOT_PAYLOAD_TABLE)
    if not isinstance(table_payload, dict):
        return ""
    return _polyglot_name_payload_value(table_payload)


def _polyglot_name_payload_value(payload: object) -> str:
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return ""
    name: object = cast(dict[str, object], payload).get(_POLYGLOT_PAYLOAD_NAME)
    return name if isinstance(name, str) else ""
