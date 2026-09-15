"""Conservative CTE output fact recovery for SQL analysis."""

from __future__ import annotations

from typing import Any, Protocol, cast

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile.constants import SQL_WILDCARD_TOKEN
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_CAST_KINDS as _POLYGLOT_CAST_KINDS
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_KIND_ALIAS as _POLYGLOT_KIND_ALIAS
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_ANNOTATED as _POLYGLOT_KIND_ANNOTATED,
)
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_KIND_COLUMN as _POLYGLOT_KIND_COLUMN
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_KIND_SELECT as _POLYGLOT_KIND_SELECT
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_KIND_TABLE as _POLYGLOT_KIND_TABLE
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_COLUMN as _POLYGLOT_PAYLOAD_COLUMN,
)
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_PAYLOAD_NAME as _POLYGLOT_PAYLOAD_NAME
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_TABLE as _POLYGLOT_PAYLOAD_TABLE,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_SET_OPERATION_KINDS as _POLYGLOT_SET_OPERATION_KINDS,
)


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


def _polyglot_cte_passthrough_type_facts(
    *,
    polyglot_module: Any,
    cleaned_sql: str,
    dialect: str | None,
    column_types_by_table: dict[str, dict[str, str]],
    inference_profile: ExpressionInferenceProfile,
    analysis: dict[str, Any],
    expression_type_resolver: _ExpressionTypeResolver,
) -> tuple[dict[str, str], frozenset[str]]:
    """Recover types that compact analysis incorrectly skips across direct CTE reads."""

    if not column_types_by_table or not analysis.get("cteFacts"):
        return {}, frozenset()
    try:
        parsed: Any = polyglot_module.parse_one(cleaned_sql, dialect=dialect or "generic")
    except polyglot_module.PolyglotError:
        return {}, frozenset()
    ctes: tuple[tuple[str, Any, bool], ...] = _polyglot_top_level_ctes(parsed)
    if not ctes:
        return {}, frozenset()
    inferred_types: dict[str, str] = _polyglot_cte_passthrough_types_from_parsed(
        parsed=parsed,
        column_types_by_table=column_types_by_table,
        inference_profile=inference_profile,
        expression_type_resolver=expression_type_resolver,
    )
    return inferred_types, _polyglot_direct_cte_output_names(
        parsed=parsed,
        cte_names=frozenset(name for name, _, _ in ctes),
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
) -> dict[str, str]:
    ctes: tuple[tuple[str, Any, bool], ...] = _polyglot_top_level_ctes(parsed)
    if not ctes:
        return {}
    relation_types: dict[str, dict[str, str]] = _polyglot_referenced_relation_facts(
        parsed=parsed,
        facts_by_table=column_types_by_table,
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
) -> dict[str, InferredNullability]:
    ctes: tuple[tuple[str, Any, bool], ...] = _polyglot_top_level_ctes(parsed)
    if not ctes:
        return {}
    relation_nullability: dict[str, dict[str, InferredNullability]] = (
        _polyglot_referenced_relation_facts(
            parsed=parsed,
            facts_by_table=column_nullability_by_table,
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
    *, parsed: Any, facts_by_table: dict[str, dict[str, T]]
) -> dict[str, dict[str, T]]:
    referenced_facts: dict[str, dict[str, T]] = {}
    for table in parsed.find_all(_POLYGLOT_KIND_TABLE):
        table_name: str = str(getattr(table, "name", "") or "")
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
    inferred: dict[str, InferredNullability] = {}
    projection: Any
    for projection in getattr(select, "expressions", ()):
        projection = _unwrap_polyglot_annotations(projection)
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
        if nullability != InferredNullability.UNKNOWN:
            inferred[output_name] = nullability
    return inferred


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
    with_payload: object = getattr(root, "args", {}).get("with")
    raw_ctes: object = (
        cast(dict[str, object], with_payload).get("ctes")
        if isinstance(with_payload, dict)
        else None
    )
    if not isinstance(raw_ctes, list):
        return ()
    cte_bodies: tuple[Any, ...] = tuple(
        child
        for child in root.children()
        if str(getattr(child, "kind", ""))
        in {_POLYGLOT_KIND_SELECT, *_POLYGLOT_SET_OPERATION_KINDS}
    )
    if len(cte_bodies) != len(raw_ctes):
        return ()
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
    branch_types: list[dict[str, str]] = []
    for side in ("left", "right"):
        branch: Any = getattr(operation, "args", {}).get(side)
        if branch is None:
            return {}
        inferred: dict[str, str] = _polyglot_select_output_types(
            select=branch,
            relation_types=relation_types,
            inference_profile=inference_profile,
            expression_type_resolver=expression_type_resolver,
        )
        branch_types.append(inferred)
    left_types, right_types = branch_types
    if bool(getattr(operation, "args", {}).get("by_name")):
        return {
            name: left_type
            for name, left_type in left_types.items()
            if _case_insensitive_mapping_get(mapping=right_types, key=name) == left_type
        }
    return {}


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
        expression_kind: str = str(getattr(expression, "kind", ""))
        inferred_type: str | None = (
            expression_type_resolver(
                expression=expression,
                inference_profile=inference_profile,
            )
            if expression_kind in _POLYGLOT_CAST_KINDS
            else None
        )
        if inferred_type is None and expression_kind == _POLYGLOT_KIND_COLUMN:
            inferred_type = _polyglot_direct_column_type(
                expression=expression,
                types_by_alias=types_by_alias,
            )
        if inferred_type is not None:
            inferred[output_name] = inferred_type
    return inferred


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
