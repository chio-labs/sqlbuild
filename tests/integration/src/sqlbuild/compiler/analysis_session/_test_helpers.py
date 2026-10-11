"""Seeded CTE queries and both CTE fact recoveries, compared function for function."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

import sqlbuild._native as native_module
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.adapter.type_system.main.conditional_result_nullability import (
    conditional_result_nullability,
)
from sqlbuild.adapter.type_system.main.first_arg_nullability import first_arg_nullability
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from sqlbuild.compiler.analysis_session._helpers.profile_rows import nullability_rule_rows

type Generate = Callable[[random.Random, list[str], int], str]
type CteFactView = (
    tuple[list[tuple[str, str]], list[tuple[str, str]], list[str], list[str]] | tuple[str, str]
)


@dataclass(frozen=True)
class CteFactQuery:
    """One generated query and the enrichment facts both recoveries read."""

    sql: str
    profile: ExpressionInferenceProfile
    recover: bool
    null_filter: bool


@dataclass
class CteFactParity:
    """Native's recovered facts for every query it answered."""

    queries: list[object]
    native: list[object]
    counts: Counter[str]


_SCHEMAS: dict[str, dict[str, str]] = {
    "orders": {
        "order_id": "INTEGER",
        "customer_id": "BIGINT",
        "qty": "INT",
        "price": "DECIMAL(10, 2)",
        "big_price": "NUMERIC(12,2)",
        "ratio": "DOUBLE",
        "status": "VARCHAR",
        "code": "VARCHAR(20)",
        "note": "TEXT",
        "flag": "BOOLEAN",
        "placed_on": "DATE",
        "placed_at": "TIMESTAMP",
        "MixedCase": "INTEGER",
        "mixedcase": "BIGINT",
        "Price": "FLOAT",
    },
    "customers": {
        "customer_id": "BIGINT",
        "order_id": "VARCHAR",
        "region": "STRING",
        "price": "DOUBLE",
        "Region": "CHAR(2)",
        "empty_type": "",
    },
    "Events": {"event_id": "INT", "kind": "VARCHAR(10)"},
    "events": {"event_id": "BIGINT", "payload": "JSON"},
}
_INPUT_SHAPES: list[tuple[str, list[tuple[str, str]]]] = [
    (table, list(columns.items())) for table, columns in _SCHEMAS.items()
]
_ADAPTERS: tuple[BaseAdapter, ...] = (
    DuckDbAdapter(),
    SnowflakeAdapter(),
    BigQueryAdapter(),
    DatabricksAdapter(),
    PostgresAdapter(),
    SqlServerAdapter(),
)
# Rules apply by node kind. The wheel parses IF, IFF and IIF as `if_func`, whose arguments
# Python never collects, so adapters' IF/IFF rules stay unknown here; the profile keyed by
# node kinds with collected arguments reaches the conditional_result and first_arg rules.
PROFILES: tuple[ExpressionInferenceProfile, ...] = (
    *(adapter.expression_inference_profile() for adapter in _ADAPTERS),
    ExpressionInferenceProfile(
        sql_analysis_dialect="duckdb",
        function_nullability_rules=DuckDbAdapter()
        .expression_inference_profile()
        .function_nullability_rules,
        function_return_types={"LENGTH": "BIGINT", "UPPER": "VARCHAR(5)", "ABS": "DECIMAL(10,2)"},
    ),
    ExpressionInferenceProfile(
        sql_analysis_dialect="snowflake",
        function_nullability_rules={
            "FUNCTION": conditional_result_nullability,
            "IN": conditional_result_nullability,
            "ARRAY_FUNC": first_arg_nullability,
            "CONCAT": first_arg_nullability,
            "UPPER": first_arg_nullability,
            "LOWER": first_arg_nullability,
        },
        function_return_types=SnowflakeAdapter()
        .expression_inference_profile()
        .function_return_types,
    ),
    ExpressionInferenceProfile(sql_analysis_dialect="generic"),
    ExpressionInferenceProfile(sql_analysis_dialect=None),
)
_TYPES: tuple[str, ...] = (
    "INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT", "DECIMAL(10, 2)", "DECIMAL(12,2)",
    "DECIMAL", "DECIMAL(9)", "NUMERIC(10, 2)", "NUMERIC", "NUMBER", "NUMBER(10, 2)", "VARCHAR",
    "VARCHAR(10)", "TEXT", "STRING", "CHAR(3)", "DOUBLE", "FLOAT", "REAL", "FLOAT64", "INT64",
    "BOOLEAN", "BOOL", "DATE", "TIMESTAMP", "TIMESTAMPTZ", "TIMESTAMP WITH TIME ZONE",
    "TIMESTAMP_NTZ", "DATETIME", "JSON", "VARIANT", "BINARY", "HUGEINT", "BIGNUMERIC",
    "NVARCHAR(5)", "DOUBLE PRECISION", "INTERVAL", "UUID", "ARRAY<INT>", "INT[]",
    "STRUCT<a INT>", "MAP(VARCHAR, INT)",
)  # fmt: skip
_LITERALS: tuple[str, ...] = ("1", "'x'", "NULL", "1.5", "TRUE", "DATE '2020-01-01'")
_MAX_DEPTH: int = 3
_ALIASES: tuple[str, ...] = ("b", "c", "o2", "X")
_JOINS: tuple[tuple[str, str], ...] = (
    ("JOIN", " ON TRUE"),
    ("LEFT JOIN", " ON TRUE"),
    ("RIGHT JOIN", " ON TRUE"),
    ("FULL OUTER JOIN", " ON TRUE"),
    ("LEFT OUTER JOIN", " ON TRUE"),
    ("INNER JOIN", " ON TRUE"),
    ("CROSS JOIN", ""),
)
_OUTPUT_NAMES: tuple[str, ...] = (
    "c{index}", "C{index}", '"Mx{index}"', "status", "qty", "dup", "Dup", '"Größe"',
    '"STRASSE"', '"straße"', "ıd",
)  # fmt: skip
_STARS: tuple[str, ...] = (
    "*",
    "{alias}.*",
    "* EXCLUDE (status)",
    "* EXCLUDE (order_id, qty)",
    "* REPLACE (1 AS qty)",
)
_SET_OPERATIONS: tuple[str, ...] = (
    "UNION ALL",
    "UNION",
    "UNION ALL BY NAME",
    "EXCEPT",
    "INTERSECT",
)
_FACT_KINDS: tuple[str, ...] = ("types", "nullability", "direct", "non_null")
_CTE_NAMES: tuple[str, ...] = ("cte{index}", "Cte{index}", '"Cte{index}"', "base", "orders")


def _quoted(rng: random.Random, name: str) -> str:
    return rng.choices((f'"{name}"', name.upper(), name.lower(), name), weights=(10, 10, 5, 75))[0]


def _column(rng: random.Random, columns: list[str]) -> str:
    return _quoted(rng, rng.choice(columns))


def _nested(rng: random.Random, columns: list[str], depth: int) -> str:
    return _expression(rng=rng, columns=columns, depth=depth + 1)


_LEAVES: tuple[Generate, ...] = (
    lambda rng, columns, depth: _column(rng, columns),
    lambda rng, columns, depth: rng.choice(_LITERALS),
)
_COMPOUNDS: tuple[Generate, ...] = (
    lambda rng, columns, depth: _column(rng, columns),
    lambda rng, columns, depth: _column(rng, columns),
    lambda r, c, d: f"CAST({_nested(r, c, d)} AS {r.choice(_TYPES)})",
    lambda r, c, d: f"TRY_CAST({_nested(r, c, d)} AS {r.choice(_TYPES)})",
    lambda r, c, d: f"{_nested(r, c, d)}::{r.choice(('INT', 'DECIMAL(5, 1)', 'VARCHAR', 'TEXT'))}",
    lambda rng, columns, depth: rng.choice(_LITERALS),
    lambda r, c, d: (
        f"CASE WHEN {_nested(r, c, d)} THEN {_nested(r, c, d)} ELSE {_nested(r, c, d)} END"
    ),
    lambda r, c, d: (
        f"CASE {_nested(r, c, d)} WHEN 1 THEN {_nested(r, c, d)} WHEN 2 THEN {_nested(r, c, d)} END"
    ),
    lambda r, c, d: f"CASE WHEN {_nested(r, c, d)} THEN {_nested(r, c, d)} END",
    lambda r, c, d: f"COALESCE({_nested(r, c, d)}, {_nested(r, c, d)})",
    lambda r, c, d: f"COALESCE({_nested(r, c, d)}, {_nested(r, c, d)}, {_nested(r, c, d)})",
    lambda r, c, d: f"NULLIF({_nested(r, c, d)}, {_nested(r, c, d)})",
    lambda r, c, d: f"IF({_nested(r, c, d)}, {_nested(r, c, d)}, {_nested(r, c, d)})",
    lambda r, c, d: f"IFF({_nested(r, c, d)}, {_nested(r, c, d)}, {_nested(r, c, d)})",
    lambda r, c, d: f"UPPER({_nested(r, c, d)})",
    lambda r, c, d: f"LOWER({_nested(r, c, d)})",
    lambda r, c, d: f"{_nested(r, c, d)} || {_nested(r, c, d)}",
    lambda r, c, d: f"SUBSTRING({_nested(r, c, d)}, 1, 2)",
    lambda r, c, d: f"{r.choice(('MAX', 'MIN', 'SUM', 'AVG', 'COUNT'))}({_nested(r, c, d)})",
    lambda r, c, d: f"MAX({_nested(r, c, d)}) OVER (PARTITION BY {_column(r, c)})",
    lambda r, c, d: f"ROW_NUMBER() OVER (ORDER BY {_column(r, c)})",
    lambda r, c, d: f"{_nested(r, c, d)} {r.choice(('>', '=', '<>', 'LIKE'))} {_nested(r, c, d)}",
    lambda r, c, d: f"{_nested(r, c, d)} IS NULL",
    lambda r, c, d: f"{_nested(r, c, d)} IS NOT NULL",
    lambda r, c, d: f"{_nested(r, c, d)} {r.choice(('+', '*', '/'))} {_nested(r, c, d)}",
    lambda r, c, d: (
        f"{r.choice(('TO_VARCHAR', 'ABS', 'LENGTH', 'REPLACE', 'CONCAT', 'TO_DATE'))}"
        f"({_nested(r, c, d)}, {_nested(r, c, d)})"
    ),
    lambda r, c, d: f"LENGTH({_nested(r, c, d)})",
    lambda r, c, d: (
        f"{r.choice(('GREATEST', 'CONCAT_WS', 'DECODE'))}({_nested(r, c, d)}, "
        f"{_nested(r, c, d)}, {_nested(r, c, d)})"
    ),
    lambda r, c, d: f"{_nested(r, c, d)} IN ({_nested(r, c, d)}, {_nested(r, c, d)})",
    lambda r, c, d: f"[{_nested(r, c, d)}, {_nested(r, c, d)}]",
)


def _expression(*, rng: random.Random, columns: list[str], depth: int) -> str:
    builders: tuple[Generate, ...] = (_LEAVES, _COMPOUNDS)[depth < _MAX_DEPTH]
    return rng.choice(builders)(rng, columns, depth)


def _star_projection(
    rng: random.Random, aliases: list[str], columns: list[str], index: int
) -> tuple[str, list[str]]:
    return rng.choice(_STARS).format(alias=aliases[0]), list(columns)


def _column_projection(
    rng: random.Random, aliases: list[str], columns: list[str], index: int
) -> tuple[str, list[str]]:
    column: str = rng.choice(columns)
    qualifier: str = rng.choices(("", f"{rng.choice(aliases)}."), weights=(6, 4))[0]
    return f"{qualifier}{_quoted(rng, column)}", [column]


def _expression_projection(
    rng: random.Random, aliases: list[str], columns: list[str], index: int
) -> tuple[str, list[str]]:
    name: str = rng.choice(_OUTPUT_NAMES).format(index=index)
    return f"{_expression(rng=rng, columns=columns, depth=0)} AS {name}", [name.strip('"')]


_PROJECTIONS: tuple[Callable[..., tuple[str, list[str]]], ...] = (
    _star_projection,
    _column_projection,
    _expression_projection,
)


def _predicate(rng: random.Random, aliases: list[str], columns: list[str]) -> str:
    qualifier: str = rng.choice(("", f"{rng.choice(aliases)}."))
    column: str = f"{qualifier}{_column(rng, columns)}"
    return rng.choice(
        (
            f"{column} IS NOT NULL",
            f"({column} IS NOT NULL)",
            f"{column} > 1",
            f"NOT {column} IS NULL",
        )
    )


def _select(
    *, rng: random.Random, relations: dict[str, list[str]], nests: bool
) -> tuple[str, list[str]]:
    first: str = rng.choice(list(relations))
    alias_sql, alias = rng.choice(((("", first)), (" a", "a"), (" AS A", "A"), (" t1", "t1")))
    columns: list[str] = list(relations[first])
    aliases: list[str] = [alias]
    joins: list[str] = []
    for _ in range(rng.choice((0, 0, 1, 1, 2))):
        other: str = rng.choice(list(relations))
        join_alias: str = rng.choice(_ALIASES)
        join, condition = rng.choice(_JOINS)
        joins.append(f"\n{join} {_quoted(rng, other)} AS {join_alias}{condition}")
        columns.extend(relations[other])
        aliases.append(join_alias)
    projections: list[str] = []
    outputs: list[str] = []
    for index in range(rng.randint(1, 5)):
        projection, names = rng.choices(_PROJECTIONS, weights=(12, 33, 55))[0](
            rng, aliases, columns, index
        )
        projections.append(projection)
        outputs.extend(names)
    predicates: list[str] = [_predicate(rng, aliases, columns) for _ in range(rng.randint(1, 3))]
    where: str = rng.choices(
        ("", "\nWHERE " + rng.choice((" AND ", " OR ", " AND ")).join(predicates)),
        weights=(3, 7),
    )[0]
    group: str = rng.choices(("", "\nGROUP BY 1"), weights=(9, 1))[0]
    body: str = (
        f"SELECT {', '.join(projections)}\nFROM {_quoted(rng, first)}{alias_sql}"
        f"{''.join(joins)}{where}{group}"
    )
    operation: Callable[[], str] = rng.choices(
        (lambda: "", lambda: _set_operation(rng=rng, relations=relations)), weights=(85, 15)
    )[0]
    selected: str = f"{body}{operation()}"
    nested: bool = nests and rng.random() < 0.15
    return (
        lambda: (selected, outputs),
        lambda: _nested_select(rng=rng, relations=relations),
    )[nested]()


def _set_operation(*, rng: random.Random, relations: dict[str, list[str]]) -> str:
    other, _ = _select(rng=rng, relations=relations, nests=False)
    return f"\n{rng.choice(_SET_OPERATIONS)}\n{other}"


def _nested_select(*, rng: random.Random, relations: dict[str, list[str]]) -> tuple[str, list[str]]:
    inner, outputs = _select(rng=rng, relations=relations, nests=False)
    return f"WITH inner_cte AS ({inner})\nSELECT * FROM inner_cte", outputs


def generated_cte_query(*, rng: random.Random) -> str:
    """A query of one to three CTEs over typed inputs and an outer select reading them."""

    relations: dict[str, list[str]] = {table: list(columns) for table, columns in _SCHEMAS.items()}
    ctes: list[str] = []
    for index in range(rng.randint(1, 3)):
        body, outputs = _select(rng=rng, relations=relations, nests=True)
        name: str = rng.choice(_CTE_NAMES).format(index=index)
        column_aliases: str = rng.choices(("", " (x, y)"), weights=(93, 7))[0]
        ctes.append(f"{name}{column_aliases} AS (\n{body}\n)")
        relations[name.strip('"')] = outputs or ["order_id"]
    cte_relations: dict[str, list[str]] = dict(
        filter(lambda item: item[0] not in _SCHEMAS or rng.random() < 0.2, relations.items())
    )
    outer, _ = _select(rng=rng, relations=cte_relations or relations, nests=False)
    return "WITH " + ",\n".join(ctes) + "\n" + outer


def generated_cte_fact_query(*, rng: random.Random) -> CteFactQuery:
    """A generated query under one adapter's profile, with enrichment's recovery gates."""

    return CteFactQuery(
        sql=generated_cte_query(rng=rng),
        profile=rng.choice(PROFILES),
        recover=rng.random() < 0.9,
        null_filter=rng.random() < 0.8,
    )


def native_cte_facts(*, query: CteFactQuery) -> tuple[str | None, CteFactView]:
    """Native recovery's deferral reason, or None and its facts."""

    deferral, types, nullability, direct, non_null = native_module._oracle_cte_fact_recovery(
        (
            query.sql,
            query.profile.sql_analysis_dialect or "generic",
            _INPUT_SHAPES,
            list(query.profile.function_return_types.items()),
            nullability_rule_rows(query.profile),
            query.recover,
            query.null_filter,
        )
    )
    return deferral, (types, nullability, direct, non_null)


def compare_cte_facts(*, query: CteFactQuery, parity: CteFactParity) -> None:
    """Record native recovery of `query` where it answers, and what it recovered."""

    deferral, native = native_cte_facts(query=query)
    answered: list[CteFactView] = [native][: int(deferral is None)]
    parity.counts.update(
        [f"deferred:{str(deferral).partition(' ')[0]}"][: int(deferral is not None)]
    )
    parity.counts["compared"] += len(answered)
    for index, kind in enumerate(_FACT_KINDS):
        parity.counts[f"recovered_{kind}"] += sum(bool(view[index]) for view in answered)
    parity.queries.extend((query.sql, query.profile.sql_analysis_dialect) for _ in answered)
    parity.native.extend(answered)
