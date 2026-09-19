"""Compiler proof for closed contracts over runtime-dynamic pivot columns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sqlbuild.compiler.compile.models import (
    DynamicColumnContractProof,
    DynamicColumnFamilyProof,
    InferredColumn,
)
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily

_DUCKDB_DIALECT: str = "duckdb"
_MOTHERDUCK_DIALECT: str = "motherduck"
_SNOWFLAKE_DIALECT: str = "snowflake"
_PIVOT_AST_KIND: str = "pivot"
_SELECT_AST_KIND: str = "select"
_QUERY_AST_KINDS: frozenset[str] = frozenset({"query", "subquery"})
_CAST_AST_KIND: str = "cast"
_COLUMN_AST_KIND: str = "column"
_TABLE_AST_KIND: str = "table"
_FUNCTION_AST_KIND: str = "function"
_ALIAS_AST_KIND: str = "alias"
_CTE_AST_KIND: str = "cte"
_STAR_AST_KIND: str = "star"
_DYNAMIC_VALUE_SOURCE_KINDS: frozenset[str] = frozenset({"pivot_any", _SELECT_AST_KIND, "query"})
_DEPENDENCY_FUNCTION_NAMES: frozenset[str] = frozenset({"__ref", "__source", "__seed"})
_UNKNOWN_DATA_TYPE: str = "UNKNOWN"
_SIMPLIFIED_PIVOT_DIALECTS: frozenset[str] = frozenset({_DUCKDB_DIALECT, _MOTHERDUCK_DIALECT})
_SUPPORTED_DIALECTS: frozenset[str] = frozenset({*_SIMPLIFIED_PIVOT_DIALECTS, _SNOWFLAKE_DIALECT})
_TYPE_PRESERVING_AGGREGATES: frozenset[str] = frozenset({"ANY_VALUE", "MAX", "MIN"})
type _CteMap = dict[str, dict[str, object] | None]


@dataclass(frozen=True)
class _ColumnFact:
    name: str
    type: str | None
    nullability: InferredNullability = InferredNullability.UNKNOWN


@dataclass(frozen=True)
class _Boundary:
    pivot: dict[str, object] | None = None
    passthrough_name: str | None = None


def analyze_dynamic_column_contract(
    *,
    query_sql: str,
    dialect: str | None,
    families: tuple[SchemaDynamicColumnFamily, ...],
    column_types_by_table: dict[str, dict[str, str]],
    authoritative_column_types_by_table: dict[str, dict[str, str]],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    dynamic_families_by_table: dict[str, tuple[SchemaDynamicColumnFamily, ...]],
) -> DynamicColumnContractProof | None:
    """Prove that a model output is closed over fixed columns and declared pivot families."""

    if not families:
        return None
    normalized_dialect: str = (dialect or "").casefold()
    if normalized_dialect not in _SUPPORTED_DIALECTS:
        return _failure(
            f"adapter dialect '{dialect or 'generic'}' does not support compiler-proven "
            "dynamic pivots"
        )
    parse_dialect: str = (
        _DUCKDB_DIALECT if normalized_dialect == _MOTHERDUCK_DIALECT else normalized_dialect
    )
    polyglot: Any = import_polyglot_sql()
    try:
        parsed: Any = polyglot.parse_one(query_sql, dialect=parse_dialect)
    except polyglot.PolyglotError as error:
        return _failure(f"dynamic pivot SQL could not be parsed: {error}")
    root: object = parsed.to_dict()
    if not isinstance(root, dict):
        return _failure("dynamic pivot SQL did not produce a structured query")
    ctes: _CteMap = _collect_ctes(root)
    boundary: _Boundary | None = _resolve_boundary(node=root, ctes=ctes, seen=frozenset())
    if boundary is None:
        return _failure(
            "output must be a wildcard projection from one supported dynamic pivot or a proven "
            "dynamic-family passthrough"
        )
    if boundary.passthrough_name is not None:
        return _analyze_passthrough(
            name=boundary.passthrough_name,
            families=families,
            column_types_by_table=column_types_by_table,
            column_nullability_by_table=column_nullability_by_table,
            dynamic_families_by_table=dynamic_families_by_table,
        )
    if boundary.pivot is None:
        return _failure("dynamic output boundary did not resolve to a pivot")
    return _analyze_pivot(
        pivot=boundary.pivot,
        dialect=normalized_dialect,
        families=families,
        ctes=ctes,
        column_types_by_table=authoritative_column_types_by_table,
        column_nullability_by_table=column_nullability_by_table,
        bare_dynamic_pivot=_node_key(root) == _PIVOT_AST_KIND,
    )


def _analyze_passthrough(
    *,
    name: str,
    families: tuple[SchemaDynamicColumnFamily, ...],
    column_types_by_table: dict[str, dict[str, str]],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    dynamic_families_by_table: dict[str, tuple[SchemaDynamicColumnFamily, ...]],
) -> DynamicColumnContractProof:
    upstream_families: tuple[SchemaDynamicColumnFamily, ...] | None = _casefold_lookup(
        mapping=dynamic_families_by_table, key=name
    )
    if upstream_families is None or not _families_equal(left=families, right=upstream_families):
        return _failure(
            f"dynamic-family passthrough from '{name}' must redeclare the upstream families exactly"
        )
    source_columns: tuple[_ColumnFact, ...] | None = _external_schema(
        name=name,
        column_types_by_table=column_types_by_table,
        column_nullability_by_table=column_nullability_by_table,
    )
    if source_columns is None:
        return _failure(f"dynamic-family passthrough source '{name}' has no authoritative schema")
    return DynamicColumnContractProof(
        output_proven=True,
        fixed_columns=tuple(
            InferredColumn(name=column.name, type=column.type, nullability=column.nullability)
            for column in source_columns
        ),
        families=tuple(
            DynamicColumnFamilyProof(name=family.name, inferred_type=family.type)
            for family in families
        ),
        input_relations=(name,),
    )


def _analyze_pivot(
    *,
    pivot: dict[str, object],
    dialect: str,
    families: tuple[SchemaDynamicColumnFamily, ...],
    ctes: _CteMap,
    column_types_by_table: dict[str, dict[str, str]],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    bare_dynamic_pivot: bool,
) -> DynamicColumnContractProof:
    if bool(pivot.get("unpivot")):
        return _failure("UNPIVOT does not produce a dynamic column family")
    pivot_columns, aggregates, dynamic, pivot_columns_valid = _pivot_components(
        pivot=pivot, dialect=dialect
    )
    if not dynamic:
        return _failure("static pivot values must use ordinary exact column declarations")
    if len(pivot_columns) != 1:
        return _failure("dynamic column contracts currently require exactly one pivot column")
    if not pivot_columns_valid:
        return _failure("dynamic pivot columns must be direct column references")
    source_node: object = pivot.get("this")
    source_columns: tuple[_ColumnFact, ...] | None = _relation_schema(
        node=source_node,
        ctes=ctes,
        column_types_by_table=column_types_by_table,
        column_nullability_by_table=column_nullability_by_table,
        seen=frozenset(),
    )
    if source_columns is None:
        return _failure("dynamic pivot input does not have an authoritative, explicit schema")
    input_relation: str | None = _external_relation_name(
        node=source_node,
        ctes=ctes,
        seen=frozenset(),
    )
    if input_relation is None:
        return _failure("dynamic pivot input relation could not be resolved")
    pivot_column: str = pivot_columns[0]
    matched_aggregate_indices: set[int] = set()
    family_proofs: list[DynamicColumnFamilyProof] = []
    for family in families:
        if not family.pivot_column.casefold() == pivot_column.casefold():
            return _failure(
                f"dynamic family '{family.name}' declares pivot_column '{family.pivot_column}' "
                f"but the output pivot uses '{pivot_column}'"
            )
        matches: list[tuple[int, str | None]] = []
        for index, aggregate in enumerate(aggregates):
            aggregate_name, value_name, inferred_type = _aggregate_fact(
                aggregate=aggregate, source_columns=source_columns
            )
            if (
                aggregate_name.casefold() == family.aggregate.casefold()
                and value_name is not None
                and value_name.casefold() == family.value_column.casefold()
            ):
                matches.append((index, inferred_type))
        if len(matches) != 1:
            return _failure(
                f"dynamic family '{family.name}' must match exactly one "
                f"{family.aggregate}({family.value_column}) pivot aggregate"
            )
        aggregate_index, inferred_type = matches[0]
        if aggregate_index in matched_aggregate_indices:
            return _failure("one pivot aggregate cannot satisfy multiple dynamic families")
        matched_aggregate_indices.add(aggregate_index)
        family_proofs.append(
            DynamicColumnFamilyProof(name=family.name, inferred_type=inferred_type)
        )
    if len(matched_aggregate_indices) != len(aggregates):
        return _failure("every dynamic pivot aggregate must have one declared column family")
    fixed_names: tuple[str, ...]
    if dialect in _SIMPLIFIED_PIVOT_DIALECTS and isinstance(pivot.get("group"), dict):
        fixed_names = tuple(
            name
            for expression in _nested_list(node=pivot.get("group"), keys=("group", "expressions"))
            if (name := _column_name(expression)) is not None
        )
    else:
        excluded: frozenset[str] = frozenset(
            {pivot_column.casefold(), *(family.value_column.casefold() for family in families)}
        )
        fixed_names = tuple(
            column.name for column in source_columns if column.name.casefold() not in excluded
        )
    source_by_name: dict[str, _ColumnFact] = {
        column.name.casefold(): column for column in source_columns
    }
    if any(name.casefold() not in source_by_name for name in fixed_names):
        return _failure("dynamic pivot grouping columns are not present in the pivot input")
    return DynamicColumnContractProof(
        output_proven=True,
        fixed_columns=tuple(
            InferredColumn(
                name=name,
                type=source_by_name[name.casefold()].type,
                nullability=source_by_name[name.casefold()].nullability,
            )
            for name in fixed_names
        ),
        families=tuple(family_proofs),
        input_relations=(input_relation,),
        bare_dynamic_pivot=bare_dynamic_pivot,
    )


def _pivot_components(
    *, pivot: dict[str, object], dialect: str
) -> tuple[tuple[str, ...], tuple[dict[str, object], ...], bool, bool]:
    if dialect in _SIMPLIFIED_PIVOT_DIALECTS and pivot.get("using"):
        pivot_expressions: tuple[dict[str, object], ...] = _dict_list(pivot.get("expressions"))
        pivot_columns: tuple[str, ...] = tuple(
            name
            for expression in pivot_expressions
            if (name := _column_name(expression)) is not None
        )
        return (
            pivot_columns,
            _dict_list(pivot.get("using")),
            not bool(pivot.get("fields")),
            len(pivot_columns) == len(pivot_expressions),
        )
    fields: tuple[dict[str, object], ...] = _dict_list(pivot.get("fields"))
    pivot_columns = tuple(
        name
        for field in fields
        if (name := _column_name(_nested(node=field, keys=("in", "this")))) is not None
    )
    dynamic: bool = _has_dynamic_value_source(fields=fields)
    return (
        pivot_columns,
        _dict_list(pivot.get("expressions")),
        dynamic,
        len(pivot_columns) == len(fields),
    )


def _has_dynamic_value_source(*, fields: tuple[dict[str, object], ...]) -> bool:
    for field in fields:
        values: tuple[dict[str, object], ...] = _nested_list(node=field, keys=("in", "expressions"))
        if any(_node_key(value) in _DYNAMIC_VALUE_SOURCE_KINDS for value in values):
            return True
    return False


def _aggregate_fact(
    *, aggregate: dict[str, object], source_columns: tuple[_ColumnFact, ...]
) -> tuple[str, str | None, str | None]:
    aggregate_name: str = _node_key(aggregate).upper()
    payload: object = aggregate.get(_node_key(aggregate))
    if not isinstance(payload, dict):
        return aggregate_name, None, None
    payload_dict: dict[str, object] = cast(dict[str, object], payload)
    authored_name: object = payload_dict.get("name")
    if isinstance(authored_name, str) and authored_name:
        aggregate_name = authored_name.upper()
    value: object = payload_dict.get("this")
    value_name: str | None = _column_name(value)
    inferred_type: str | None = None
    if _node_key(value) == _CAST_AST_KIND:
        cast_payload: object = (
            cast(dict[str, object], value).get("cast") if isinstance(value, dict) else None
        )
        if isinstance(cast_payload, dict):
            cast_payload_dict: dict[str, object] = cast(dict[str, object], cast_payload)
            value_name = _column_name(cast_payload_dict.get("this"))
            if aggregate_name in _TYPE_PRESERVING_AGGREGATES:
                inferred_type = _render_type(cast_payload_dict.get("to"))
    if inferred_type is None and aggregate_name in _TYPE_PRESERVING_AGGREGATES:
        source_by_name: dict[str, _ColumnFact] = {
            column.name.casefold(): column for column in source_columns
        }
        source: _ColumnFact | None = (
            source_by_name.get(value_name.casefold()) if value_name is not None else None
        )
        inferred_type = source.type if source is not None else None
    return aggregate_name, value_name, inferred_type


def _resolve_boundary(*, node: object, ctes: _CteMap, seen: frozenset[str]) -> _Boundary | None:
    key: str = _node_key(node)
    payload: object = cast(dict[str, object], node).get(key) if isinstance(node, dict) else None
    if key == _PIVOT_AST_KIND and isinstance(payload, dict):
        return _Boundary(pivot=cast(dict[str, object], payload))
    if key in _QUERY_AST_KINDS and isinstance(payload, dict):
        return _resolve_boundary(
            node=cast(dict[str, object], payload).get("this"), ctes=ctes, seen=seen
        )
    if key != _SELECT_AST_KIND or not isinstance(payload, dict):
        return None
    payload_dict: dict[str, object] = cast(dict[str, object], payload)
    if payload_dict.get("joins") or not _is_single_wildcard(payload_dict.get("expressions")):
        return None
    relations: tuple[dict[str, object], ...] = _nested_dict_list(
        node=payload_dict.get("from"), key="expressions"
    )
    if len(relations) != 1:
        return None
    relation: dict[str, object] = relations[0]
    if _node_key(relation) == _PIVOT_AST_KIND:
        pivot_payload: object = relation.get("pivot")
        return (
            _Boundary(pivot=cast(dict[str, object], pivot_payload))
            if isinstance(pivot_payload, dict)
            else None
        )
    relation_name: str | None = _relation_name(relation)
    if relation_name is None:
        return None
    normalized_name: str = relation_name.casefold()
    if normalized_name in ctes:
        cte: dict[str, object] | None = ctes[normalized_name]
        if cte is None:
            return None
        if relation_name.casefold() in seen:
            return None
        resolved: _Boundary | None = _resolve_boundary(
            node=cte,
            ctes=ctes,
            seen=seen | {relation_name.casefold()},
        )
        if resolved is None:
            return None
        return resolved
    return _Boundary(passthrough_name=relation_name)


def _relation_schema(
    *,
    node: object,
    ctes: _CteMap,
    column_types_by_table: dict[str, dict[str, str]],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    seen: frozenset[str],
) -> tuple[_ColumnFact, ...] | None:
    relation_name: str | None = _relation_name(node)
    if relation_name is None:
        return None
    normalized_name: str = relation_name.casefold()
    if normalized_name not in ctes:
        return _external_schema(
            name=relation_name,
            column_types_by_table=column_types_by_table,
            column_nullability_by_table=column_nullability_by_table,
        )
    cte: dict[str, object] | None = ctes[normalized_name]
    if cte is None or normalized_name in seen:
        return None
    return _select_schema(
        node=cte,
        ctes=ctes,
        column_types_by_table=column_types_by_table,
        column_nullability_by_table=column_nullability_by_table,
        seen=seen | {normalized_name},
    )


def _external_relation_name(
    *,
    node: object,
    ctes: _CteMap,
    seen: frozenset[str],
) -> str | None:
    key: str = _node_key(node)
    payload: object = cast(dict[str, object], node).get(key) if isinstance(node, dict) else None
    if key in _QUERY_AST_KINDS and isinstance(payload, dict):
        return _external_relation_name(
            node=cast(dict[str, object], payload).get("this"),
            ctes=ctes,
            seen=seen,
        )
    if key == _SELECT_AST_KIND and isinstance(payload, dict):
        payload_dict: dict[str, object] = cast(dict[str, object], payload)
        if payload_dict.get("joins"):
            return None
        relations: tuple[dict[str, object], ...] = _nested_dict_list(
            node=payload_dict.get("from"), key="expressions"
        )
        if len(relations) != 1:
            return None
        return _external_relation_name(node=relations[0], ctes=ctes, seen=seen)
    relation_name: str | None = _relation_name(node)
    if relation_name is None:
        return None
    normalized_name: str = relation_name.casefold()
    if normalized_name not in ctes:
        return relation_name
    cte: dict[str, object] | None = ctes[normalized_name]
    if cte is None or normalized_name in seen:
        return None
    return _external_relation_name(
        node=cte,
        ctes=ctes,
        seen=seen | {normalized_name},
    )


def _select_schema(
    *,
    node: object,
    ctes: _CteMap,
    column_types_by_table: dict[str, dict[str, str]],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    seen: frozenset[str],
) -> tuple[_ColumnFact, ...] | None:
    key: str = _node_key(node)
    payload: object = cast(dict[str, object], node).get(key) if isinstance(node, dict) else None
    if key in _QUERY_AST_KINDS and isinstance(payload, dict):
        return _select_schema(
            node=cast(dict[str, object], payload).get("this"),
            ctes=ctes,
            column_types_by_table=column_types_by_table,
            column_nullability_by_table=column_nullability_by_table,
            seen=seen,
        )
    if key != _SELECT_AST_KIND or not isinstance(payload, dict):
        return None
    payload_dict: dict[str, object] = cast(dict[str, object], payload)
    if payload_dict.get("joins"):
        return None
    relations: tuple[dict[str, object], ...] = _nested_dict_list(
        node=payload_dict.get("from"), key="expressions"
    )
    if len(relations) != 1:
        return None
    source: tuple[_ColumnFact, ...] | None = _relation_schema(
        node=relations[0],
        ctes=ctes,
        column_types_by_table=column_types_by_table,
        column_nullability_by_table=column_nullability_by_table,
        seen=seen,
    )
    if source is None:
        return None
    expressions: object = payload_dict.get("expressions")
    if _is_single_wildcard(expressions):
        return source
    if not isinstance(expressions, list):
        return None
    source_by_name: dict[str, _ColumnFact] = {column.name.casefold(): column for column in source}
    output: list[_ColumnFact] = []
    for raw_expression in expressions:
        if not isinstance(raw_expression, dict):
            return None
        output_name, expression = _projection(cast(dict[str, object], raw_expression))
        source_name: str | None
        expression_type: str | None = None
        if _node_key(expression) == _CAST_AST_KIND:
            cast_payload: object = expression.get("cast")
            if not isinstance(cast_payload, dict):
                return None
            cast_payload_dict: dict[str, object] = cast(dict[str, object], cast_payload)
            source_name = _column_name(cast_payload_dict.get("this"))
            expression_type = _render_type(cast_payload_dict.get("to"))
        else:
            source_name = _column_name(expression)
        if output_name is None or source_name is None:
            return None
        source_column: _ColumnFact | None = source_by_name.get(source_name.casefold())
        if source_column is None:
            return None
        if expression_type is None:
            expression_type = source_column.type
        output.append(
            _ColumnFact(
                name=output_name,
                type=expression_type,
                nullability=source_column.nullability,
            )
        )
    return tuple(output)


def _external_schema(
    *,
    name: str,
    column_types_by_table: dict[str, dict[str, str]],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
) -> tuple[_ColumnFact, ...] | None:
    types: dict[str, str] | None = _casefold_lookup(mapping=column_types_by_table, key=name)
    if types is None:
        return None
    nullability: dict[str, InferredNullability] = (
        _casefold_lookup(mapping=column_nullability_by_table, key=name) or {}
    )
    nullability_by_name: dict[str, InferredNullability] = {
        column_name.casefold(): value for column_name, value in nullability.items()
    }
    return tuple(
        _ColumnFact(
            name=column_name,
            type=None if data_type == _UNKNOWN_DATA_TYPE else data_type,
            nullability=nullability_by_name.get(
                column_name.casefold(), InferredNullability.UNKNOWN
            ),
        )
        for column_name, data_type in types.items()
    )


def _collect_ctes(root: dict[str, object]) -> _CteMap:
    key: str = _node_key(root)
    payload: object = root.get(key)
    if not isinstance(payload, dict):
        return {}
    payload_dict: dict[str, object] = cast(dict[str, object], payload)
    with_payload: object = payload_dict.get("with")
    if not isinstance(with_payload, dict):
        return {}
    with_payload_dict: dict[str, object] = cast(dict[str, object], with_payload)
    ctes: _CteMap = {}
    for cte in _dict_list(with_payload_dict.get("ctes")):
        cte_payload: object = cte.get("cte") if _node_key(cte) == _CTE_AST_KIND else cte
        if not isinstance(cte_payload, dict):
            continue
        cte_payload_dict: dict[str, object] = cast(dict[str, object], cte_payload)
        name: str | None = _identifier_name(cte_payload_dict.get("alias"))
        query: object = cte_payload_dict.get("this")
        if name is None:
            continue
        if cte_payload_dict.get("columns"):
            ctes[name.casefold()] = None
        elif isinstance(query, dict):
            ctes[name.casefold()] = cast(dict[str, object], query)
    return ctes


def _projection(node: dict[str, object]) -> tuple[str | None, dict[str, object]]:
    if _node_key(node) != _ALIAS_AST_KIND:
        return _column_name(node), node
    payload: object = node.get("alias")
    if not isinstance(payload, dict):
        return None, node
    payload_dict: dict[str, object] = cast(dict[str, object], payload)
    expression: object = payload_dict.get("this")
    return (
        _identifier_name(payload_dict.get("alias")),
        cast(dict[str, object], expression) if isinstance(expression, dict) else {},
    )


def _relation_name(node: object) -> str | None:
    key: str = _node_key(node)
    payload: object = cast(dict[str, object], node).get(key) if isinstance(node, dict) else None
    if not isinstance(payload, dict):
        return None
    payload_dict: dict[str, object] = cast(dict[str, object], payload)
    if key == _TABLE_AST_KIND:
        return _identifier_name(payload_dict.get("name"))
    if key == _COLUMN_AST_KIND:
        return _identifier_name(payload_dict.get("name"))
    if (
        key == _FUNCTION_AST_KIND
        and str(payload_dict.get("name", "")).casefold() in _DEPENDENCY_FUNCTION_NAMES
    ):
        arguments: tuple[dict[str, object], ...] = _dict_list(payload_dict.get("args"))
        return _column_name(arguments[0]) if arguments else None
    return None


def _column_name(node: object) -> str | None:
    key: str = _node_key(node)
    payload: object = cast(dict[str, object], node).get(key) if isinstance(node, dict) else None
    if key == _COLUMN_AST_KIND and isinstance(payload, dict):
        return _identifier_name(cast(dict[str, object], payload).get("name"))
    return None


def _identifier_name(node: object) -> str | None:
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return None
    value: object = cast(dict[str, object], node).get("name")
    return value if isinstance(value, str) and value else None


def _render_type(node: object) -> str | None:
    if not isinstance(node, dict):
        return None
    node_dict: dict[str, object] = cast(dict[str, object], node)
    raw_type: object = node_dict.get("data_type")
    if not isinstance(raw_type, str) or not raw_type:
        return None
    names: dict[str, str] = {
        "big_int": "BIGINT",
        "bool": "BOOLEAN",
        "boolean": "BOOLEAN",
        "decimal": "DECIMAL",
        "double": "DOUBLE",
        "float": "FLOAT",
        "int": "INT",
        "integer": "INT",
        "text": "TEXT",
        "timestamp": "TIMESTAMP",
        "var_char": "VARCHAR",
        "varchar": "VARCHAR",
    }
    rendered: str = names.get(raw_type.casefold(), raw_type.replace("_", " ").upper())
    precision: object = node_dict.get("precision")
    scale: object = node_dict.get("scale")
    length: object = node_dict.get("length")
    if isinstance(length, int):
        return f"{rendered}({length})"
    if isinstance(precision, int):
        return (
            f"{rendered}({precision}, {scale})"
            if isinstance(scale, int)
            else f"{rendered}({precision})"
        )
    return rendered


def _families_equal(
    *,
    left: tuple[SchemaDynamicColumnFamily, ...],
    right: tuple[SchemaDynamicColumnFamily, ...],
) -> bool:
    def normalize(family: SchemaDynamicColumnFamily) -> tuple[str, str, str, str, str, str | None]:
        return (
            family.name.casefold(),
            family.pivot_column.casefold(),
            family.value_column.casefold(),
            family.aggregate.casefold(),
            family.type.casefold(),
            family.name_pattern,
        )

    return tuple(map(normalize, left)) == tuple(map(normalize, right))


def _failure(reason: str) -> DynamicColumnContractProof:
    return DynamicColumnContractProof(output_proven=False, failure_reason=reason)


def _node_key(node: object) -> str:
    if not isinstance(node, dict) or len(node) != 1:
        return ""
    return str(next(iter(node)))


def _dict_list(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(cast(dict[str, object], item) for item in value if isinstance(item, dict))


def _nested(*, node: object, keys: tuple[str, ...]) -> object:
    current: object = node
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = cast(dict[str, object], current).get(key)
    return current


def _nested_list(*, node: object, keys: tuple[str, ...]) -> tuple[dict[str, object], ...]:
    return _dict_list(_nested(node=node, keys=keys))


def _nested_dict_list(*, node: object, key: str) -> tuple[dict[str, object], ...]:
    return _dict_list(cast(dict[str, object], node).get(key) if isinstance(node, dict) else None)


def _is_single_wildcard(value: object) -> bool:
    expressions: tuple[dict[str, object], ...] = _dict_list(value)
    if len(expressions) != 1 or _node_key(expressions[0]) != _STAR_AST_KIND:
        return False
    payload: object = expressions[0].get("star")
    if not isinstance(payload, dict):
        return False
    star: dict[str, object] = cast(dict[str, object], payload)
    return not any(star.get(key) for key in ("except", "replace", "rename", "table"))


def _casefold_lookup[ValueT](*, mapping: dict[str, ValueT], key: str) -> ValueT | None:
    requested: str = key.casefold()
    for candidate, value in mapping.items():
        if candidate.casefold() == requested:
            return value
    return None
