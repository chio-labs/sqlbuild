from __future__ import annotations

import json
import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from itertools import chain
from pathlib import Path
from typing import Any, cast

import pytest

import sqlbuild._native as native_module
import sqlbuild.compiler.compile._helpers.assembly.project as assembly_project
import sqlbuild.compiler.semantic_checks._helpers.stage as semantic_stage
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile._helpers.assembly.metadata_validation import (
    get_semantic_metadata_diagnostics,
)
from sqlbuild.compiler.compile._helpers.diagnostics.recovery import (
    complete_semantic_diagnostics,
)
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject, CompilerDiagnostic
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.semantic_checks._helpers.metadata import native_metadata_diagnostics
from sqlbuild.compiler.semantic_checks._helpers.payloads import session_fact_models
from sqlbuild.compiler.semantic_checks.main._complete_native_semantic_diagnostics import (
    complete_native_semantic_diagnostics,
)
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic
from tests.integration.src.sqlbuild.compiler.analysis_session.helpers import (
    generated_analysis_files,
)

_RELATIONS: dict[str, tuple[str, ...]] = {
    '__source("raw_orders")': (
        "order_id",
        "customer_id",
        "amount",
        "status",
        "ordered_at",
        "order_date",
    ),
}
_SOURCES: str = """sources:
  - name: raw_orders
    description: Orders feed.
    expression: >-
      (SELECT 1 AS order_id, 10 AS customer_id, CAST(5 AS DOUBLE) AS amount, 'placed' AS status,
      TIMESTAMP '2026-01-01 00:00:00' AS ordered_at, DATE '2026-01-01' AS order_date)
    columns:
      - name: order_id
        type: INTEGER
      - name: customer_id
        type: INTEGER
      - name: amount
        type: DOUBLE
      - name: status
        type: VARCHAR
      - name: ordered_at
        type: TIMESTAMP
      - name: order_date
        type: DATE
"""
_OPT_OUT_SHARE: float = 0.2
_TYPO_SHARE: float = 0.45
_MIN_TYPO_LENGTH: int = 4
_ALIASES: tuple[tuple[str, str], ...] = (("", ""), ("o.", " AS o"))
_SETTINGS: tuple[str, str] = ("", "\n[settings]\nrequire_sql_analysis = true\n")
_OPT_OUTS: tuple[str, str] = ("", ", sql_analysis false")
_COMPLETION_STATUSES: tuple[str, str] = ("completion_native", "completion_deferred")
_SOURCE_COMPARISON_SHARE: float = 0.6

type _Template = Callable[[random.Random, str, tuple[str, ...]], tuple[str, tuple[str, ...]]]


@dataclass(frozen=True)
class SemanticInputs:
    """The arguments the Python compile passed to `complete_semantic_diagnostics`."""

    project: CompiledProject
    profile: ExpressionInferenceProfile
    binding_results: dict[str, tuple[SqlBindingDiagnostic, ...]]
    resource_sql_analysis: bool
    native_session: Any | None = None


def _typo(rng: random.Random, column: str) -> str:
    index: int = rng.randrange(1, max(len(column) - 2, 2))
    swapped: str = (
        column[:index] + column[index + 1 : index + 2] + column[index] + column[index + 2 :]
    )
    return (column, swapped)[len(column) >= _MIN_TYPO_LENGTH and rng.random() < _TYPO_SHARE]


def _projection(
    rng: random.Random, relation: str, columns: tuple[str, ...]
) -> tuple[str, tuple[str, ...]]:
    picked: list[str] = rng.sample(list(columns), k=min(len(columns), rng.randint(2, 4)))
    written: list[str] = [_typo(rng, column) for column in picked]
    prefix, suffix = rng.choice(_ALIASES)
    sql: str = f"SELECT {', '.join(prefix + name for name in written)}\nFROM {relation}{suffix}"
    intended: tuple[str, ...] = tuple(
        rng.choice((name, meant)) for name, meant in zip(written, picked, strict=True)
    )
    return sql, intended


def _comparison(
    rng: random.Random, relation: str, columns: tuple[str, ...]
) -> tuple[str, tuple[str, ...]]:
    relation, columns = ((relation, columns), next(iter(_RELATIONS.items())))[
        rng.random() < _SOURCE_COMPARISON_SHARE
    ]
    column: str = rng.choice(columns)
    literal: str = rng.choice(("5", "'placed'", "DATE '2026-01-01'", "TIMESTAMP '2026-01-01'"))
    kept: tuple[str, ...] = tuple(dict.fromkeys((columns[0], column)))
    sql: str = (
        f"SELECT {', '.join('o.' + name for name in kept)}\nFROM {relation} AS o\n"
        f"WHERE o.{_typo(rng, column)} > {literal}"
    )
    return sql, kept


def _arithmetic(
    rng: random.Random, relation: str, columns: tuple[str, ...]
) -> tuple[str, tuple[str, ...]]:
    left, right = rng.sample(list(columns), k=2)
    sql: str = f"SELECT {columns[0]}, {left} + {right} AS {left}\nFROM {relation}"
    return sql, tuple(dict.fromkeys((columns[0], left)))


def _aggregate(
    rng: random.Random, relation: str, columns: tuple[str, ...]
) -> tuple[str, tuple[str, ...]]:
    key, value = rng.sample(list(columns), k=2)
    sql: str = (
        f"WITH base AS (\n  SELECT {key}, {_typo(rng, value)} FROM {relation}\n)\n"
        f"SELECT {key}, MAX({value}) AS {value}\nFROM base\nGROUP BY 1"
    )
    return sql, (key, value)


_TEMPLATES: tuple[_Template, ...] = (_projection, _comparison, _arithmetic, _aggregate)


def _has_two_columns(relation: tuple[str, tuple[str, ...]]) -> bool:
    return len(relation[1]) > 1


def generated_semantic_files(
    *, rng: random.Random, model_count: int, require_analysis: bool
) -> dict[str, str]:
    """A project whose models chain through typos, temporal comparisons and type errors."""

    settings: str = _SETTINGS[require_analysis]
    files: dict[str, str] = {
        "sqlbuild_project.toml": (
            'name = "orders_semantics"\nadapter = "duckdb"\n\n[connection]\n'
            f'database = "orders.duckdb"\n{settings}'
        ),
        "sources/raw.yml": _SOURCES,
    }
    relations: list[tuple[str, tuple[str, ...]]] = list(_RELATIONS.items())
    for index in range(model_count):
        relation, columns = rng.choice(list(filter(_has_two_columns, relations)))
        sql, outputs = _TEMPLATES[index % len(_TEMPLATES)](rng, relation, columns)
        name: str = f"orders_model_{index}"
        opt_out: str = _OPT_OUTS[rng.random() < _OPT_OUT_SHARE]
        files[f"models/layer_{index % 3}/{name}.sql"] = (
            f'MODEL (description "Generated orders model {index}"{opt_out});\n\n{sql}\n'
        )
        relations.append((f'__ref("{name}")', outputs))
    return files


def captured_semantic_inputs(
    *,
    project_dir: Path,
    files: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    engine: str = "python",
) -> SemanticInputs:
    """Compile with `engine` and keep the semantic completion stage's inputs."""

    for relative_path, contents in files.items():
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")
    captured: list[SemanticInputs] = []

    def capture(**arguments: Any) -> CompiledProject:
        captured.append(SemanticInputs(**arguments))
        return complete_semantic_diagnostics(**arguments)

    with monkeypatch.context() as patch:
        patch.setenv(COMPILER_ENGINE_ENV_VAR, engine)
        patch.setattr(assembly_project, "complete_semantic_diagnostics", capture)
        _ = build_project_graph(
            discovered_inputs=discover_project_inputs(project_dir=project_dir),
            adapter=DuckDbAdapter(),
        )
    return captured[0]


def with_dialect(inputs: SemanticInputs, dialect: str) -> SemanticInputs:
    """The same stage inputs read under another SQL dialect."""

    return replace(
        inputs,
        project=replace(inputs.project, sql_analysis_dialect=dialect),
        profile=replace(inputs.profile, sql_analysis_dialect=dialect),
    )


def python_completion(
    *, inputs: SemanticInputs, monkeypatch: pytest.MonkeyPatch
) -> CompiledProject:
    """The Python engine's completed project."""

    with monkeypatch.context() as patch:
        patch.setenv(COMPILER_ENGINE_ENV_VAR, "python")
        return complete_semantic_diagnostics(
            project=inputs.project,
            profile=inputs.profile,
            binding_results=inputs.binding_results,
            resource_sql_analysis=inputs.resource_sql_analysis,
        )


def completed_natively(inputs: SemanticInputs) -> CompiledProject:
    """The native stage's completed project, which must not defer."""

    project: CompiledProject | None = native_completion(inputs)
    assert project is not None
    return project


def note_kinds(project: CompiledProject, kinds: tuple[str, ...]) -> Counter[str]:
    """How many notes of each kind the project's diagnostics carry."""

    notes: list[str] = list(chain.from_iterable(item.notes for item in project.diagnostics))
    counts: Counter[str] = Counter()
    for kind in kinds:
        counts[kind] = sum(kind in note for note in notes)
    return counts


def native_completion(inputs: SemanticInputs) -> CompiledProject | None:
    """The native stage's completed project, or None when it defers."""

    return complete_native_semantic_diagnostics(
        project=inputs.project,
        profile=inputs.profile,
        binding_results=inputs.binding_results,
        resource_sql_analysis=inputs.resource_sql_analysis,
        session=inputs.native_session,
    )


def session_corpus_files(*, corpus: str, rng: random.Random, model_count: int) -> dict[str, str]:
    """One generated project from the failing-semantics or the analysis-session corpus."""

    generators: dict[str, Callable[[], dict[str, str]]] = {
        "semantic": lambda: generated_semantic_files(
            rng=rng, model_count=model_count, require_analysis=False
        ),
        "analysis": lambda: generated_analysis_files(rng=rng, model_count=model_count),
    }
    return generators[corpus]()


def proven_output_count(project: CompiledProject) -> int:
    """How many models a dynamic pivot proof gave their output names."""

    return sum(
        model.dynamic_column_contract is not None and model.dynamic_column_contract.output_proven
        for model in project.models
    )


def without_session(inputs: SemanticInputs) -> SemanticInputs:
    """The same stage inputs with every model's output names and lineage in the payload."""

    return replace(inputs, native_session=None)


def record_session_models(*, monkeypatch: pytest.MonkeyPatch) -> list[frozenset[str]]:
    """Keep each completion's models whose output names and lineage the session supplies."""

    selections: list[frozenset[str]] = []

    def recorded(**arguments: Any) -> frozenset[str]:
        selected: frozenset[str] = session_fact_models(**arguments)
        selections.append(selected)
        return selected

    monkeypatch.setattr(semantic_stage, "session_fact_models", recorded)
    return selections


def completion_view(project: CompiledProject) -> tuple[object, ...]:
    """Everything the stage decides: diagnostics and each model's binding and type facts."""

    return (
        project.diagnostics,
        tuple(_model_view(model) for model in project.models),
    )


def _model_view(model: CompiledModel) -> tuple[object, ...]:
    return (
        model.name,
        model.binding_diagnostics,
        model.inferred_columns,
        model.unchecked_output_columns,
    )


def record_native_statuses(*, monkeypatch: pytest.MonkeyPatch) -> Counter[str]:
    """Count native type recovery plans and completed or deferred completions."""

    statuses: Counter[str] = Counter()
    plan: Callable[..., Any] = native_module.plan_semantic_type_recovery
    complete: Callable[..., Any] = native_module.complete_semantic_checks

    def counted_plan(*arguments: Any) -> Any:
        recovery: Any = plan(*arguments)
        statuses[f"type_recovery_{recovery.status}"] += 1
        return recovery

    def counted_complete(*arguments: Any) -> Any:
        outcome: Any = complete(*arguments)
        statuses[_COMPLETION_STATUSES[outcome[0] is not None]] += 1
        statuses["diagnostics_native"] += len(outcome[1])
        return outcome

    monkeypatch.setattr(native_module, "plan_semantic_type_recovery", counted_plan)
    monkeypatch.setattr(native_module, "complete_semantic_checks", counted_complete)
    return statuses


def deferral_records(record_dir: Path) -> tuple[tuple[str, str], ...]:
    """Every `(kind, site)` deferral the native stage recorded below `record_dir`."""

    records: list[tuple[str, str]] = []
    for path in sorted(record_dir.glob("analysis-deferrals-*.jsonl")):
        for line in path.read_text("utf-8").splitlines():
            record: dict[str, str] = json.loads(line)
            records.append((record["kind"], record["site"]))
    return tuple(records)


_SOURCE_COLUMNS: tuple[str, ...] = (
    "order_id",
    "customer_id",
    "amount",
    "status",
    "ordered_at",
    "order_date",
)
_MODEL_COLUMNS: tuple[str, ...] = ("order_id", "customer_id", "ordered_at", "value")
_FUNCTIONS: dict[str, tuple[str, str, str, int]] = {
    "scaled_amount": ("p_amount DOUBLE, p_factor INTEGER", "DOUBLE", "p_amount * p_factor", 2),
    "label_status": ("p_status VARCHAR", "VARCHAR", "UPPER(p_status)", 1),
    "days_since": ("p_at TIMESTAMP", "INTEGER", "DATE_DIFF('day', p_at, NOW())", 1),
}
_ARGUMENTS: tuple[str, ...] = (
    "o.{column}",
    "{column}",
    "x.{column}",
    "'x'",
    "2",
    "2.5",
    "CAST({column} AS VARCHAR)",
    "CAST({column} AS DECIMAL(10, 2))",
    "TRUE",
    "{column} = 1",
)
_ARITY_CHANGES: tuple[int, ...] = (0, 0, 0, 1, -1)
_UNIQUE_KEYS: tuple[str, ...] = ("order_id", "customer_id", "order_key")
_CURSORS: tuple[str, ...] = ("ordered_at", "customer_id", "value", "placed_at")
_CURSOR_TYPES: tuple[str, ...] = ("timestamp", "integer")
_GRAINS: dict[str, str] = {"timestamp": "  cursor_grain day,\n"}
_INPUT_COLUMNS: tuple[str, ...] = ("ordered_at", "order_id", "created_at")
_LOADED_CURSORS: tuple[str, ...] = ("load_seq", "Load_Seq", "loaded_at")
_LOADED_SOURCE: str = (
    "  - name: raw_events\n    description: Loaded events.\n    managed: true\n"
    "    write_strategy: append\n    contract: enforced\n    cursor_column: {cursor}\n"
    "    columns:\n"
    "      - name: event_id\n        type: INTEGER\n"
    "      - name: load_seq\n        type: INTEGER\n"
)
_LOADER: str = (
    "from sqlbuild.loaders import loader\n\n\n@loader\n"
    "def raw_events(ctx):\n    '''Load events.'''\n    return [{'event_id': 1, 'load_seq': 1}]\n"
)
_FIXTURE_EXTRAS: tuple[str, ...] = ("", ", 2 AS discount")
_EXPECTED_EXTRAS: tuple[str, ...] = ("", ", 3 AS Customer_ID", ", 2 AS refund")
_CTE_SHARE: float = 0.3
_AUDITS: tuple[str, ...] = (
    "",
    "  columns (\n    customer_id (audits [accepted_values (values [DATE '2026-01-01'])]),\n  ),\n",
    '  columns (\n    order_id (audits [relationships (to __ref("orders_model_0"),'
    " field order_key)]),\n  ),\n",
)
_SOURCE_SQL: str = (
    "    expression: >-\n"
    "      (SELECT 1 AS order_id, 10 AS customer_id, CAST(5 AS DOUBLE) AS amount, 'placed' AS"
    " status,\n      TIMESTAMP '2026-01-01 00:00:00' AS ordered_at, DATE '2026-01-01' AS"
    " order_date)\n    columns:\n"
)
_SOURCE_TYPES: tuple[str, ...] = ("INTEGER", "INTEGER", "DOUBLE", "VARCHAR", "TIMESTAMP", "DATE")

type _Relation = tuple[str, str, tuple[str, ...]]


def _function_file(name: str) -> str:
    arguments, returns, body, _ = _FUNCTIONS[name]
    return (
        f'FUNCTION (\n  description "Generated {name}",\n  arguments ({arguments}),\n'
        f"  returns {returns},\n);\n\n{body}\n"
    )


def _call(rng: random.Random, columns: tuple[str, ...], alias: str) -> str:
    name: str = rng.choice(tuple(_FUNCTIONS))
    count: int = max(0, _FUNCTIONS[name][3] + rng.choice(_ARITY_CHANGES))
    arguments: list[str] = [
        rng.choice(_ARGUMENTS).format(column=rng.choice(columns)).replace("o.", f"{alias}.")
        for _ in range(count)
    ]
    return f'__udf("{name}")({", ".join(arguments)})'


def _query(rng: random.Random, relation: _Relation) -> str:
    reference, _, columns = relation
    plain: str = (
        "SELECT o.order_id, o.customer_id, o.ordered_at, "
        f"{_call(rng, columns, 'o')} AS value\nFROM {reference} AS o"
    )
    with_cte: str = (
        f"WITH base AS (\n  SELECT * FROM {reference} AS o\n)\n"
        f"SELECT b.order_id, b.customer_id, b.ordered_at, {_call(rng, columns, 'b')} AS value\n"
        "FROM base AS b"
    )
    return (plain, with_cte)[rng.random() < _CTE_SHARE]


def _header(rng: random.Random, index: int, relation: _Relation) -> str:
    _, upstream, _ = relation
    cursor_type: str = rng.choice(_CURSOR_TYPES)
    incremental: str = (
        "  materialized incremental,\n  incremental_strategy delete_insert,\n"
        f"  unique_key [order_id],\n  cursor {rng.choice(_CURSORS)},\n"
        f"  cursor_type {cursor_type},\n{_GRAINS.get(cursor_type, '')}"
        f"  cursor_inputs (\n    {upstream} {rng.choice(_INPUT_COLUMNS)},\n  ),\n"
    )
    table: str = f"  materialized table,\n  unique_key [{rng.choice(_UNIQUE_KEYS)}],\n"
    configs: tuple[str, str, str] = (table, incremental, "")
    kind: int = (index % 3, 0)[index % 3 == 1 and not upstream]
    return configs[kind] + rng.choice(_AUDITS)


def generated_metadata_files(*, rng: random.Random, model_count: int) -> dict[str, str]:
    """A project calling declared functions, with config, source cursor and SQL test metadata."""

    columns: str = "".join(
        f"      - name: {name}\n        type: {kind}\n"
        for name, kind in zip(_SOURCE_COLUMNS, _SOURCE_TYPES, strict=True)
    )
    files: dict[str, str] = {
        "sqlbuild_project.toml": (
            'name = "orders_metadata"\nadapter = "duckdb"\n\n[connection]\n'
            'database = "orders.duckdb"\n'
        ),
        "sources/raw.yml": (
            "sources:\n  - name: raw_orders\n    description: Orders feed.\n"
            f"{_SOURCE_SQL}{columns}{_LOADED_SOURCE.format(cursor=rng.choice(_LOADED_CURSORS))}"
        ),
        "python/loaders/raw_events.py": _LOADER,
        "tests/unit/test_orders_model_0.sql": (
            "TEST();\n\nWITH\n__source__raw_orders AS (\n"
            "  SELECT 1 AS order_id, 10 AS customer_id, CAST(5 AS DOUBLE) AS amount,"
            " 'placed' AS status, TIMESTAMP '2026-01-01' AS ordered_at,"
            f" DATE '2026-01-01' AS order_date{rng.choice(_FIXTURE_EXTRAS)}\n),\n"
            "__expected__orders_model_0 AS (\n"
            f"  SELECT 1 AS order_id{rng.choice(_EXPECTED_EXTRAS)}\n)\nSELECT 1\n"
        ),
    }
    for name in _FUNCTIONS:
        files[f"functions/sql/{name}.sql"] = _function_file(name)
    relations: list[_Relation] = [('__source("raw_orders")', "", _SOURCE_COLUMNS)]
    for index in range(model_count):
        relation: _Relation = rng.choice(relations)
        name: str = f"orders_model_{index}"
        files[f"models/layer_{index % 3}/{name}.sql"] = (
            f'MODEL (\n  description "Generated orders model {index}",\n'
            f"{_header(rng, index, relation)});\n\n{_query(rng, relation)}\n"
        )
        relations.append((f'__ref("{name}")', name, _MODEL_COLUMNS))
    return files


def python_metadata(
    *, inputs: SemanticInputs, monkeypatch: pytest.MonkeyPatch
) -> tuple[CompilerDiagnostic, ...]:
    """The Python engine's metadata diagnostics."""

    with monkeypatch.context() as patch:
        patch.setenv(COMPILER_ENGINE_ENV_VAR, "python")
        return get_semantic_metadata_diagnostics(
            project=inputs.project,
            profile=inputs.profile,
            resource_sql_analysis=inputs.resource_sql_analysis,
        )


def native_metadata(inputs: SemanticInputs) -> tuple[CompilerDiagnostic, ...] | None:
    """The native stage's metadata diagnostics, or None when it defers."""

    catalog: Any = cast(Any, inputs.project.binding_catalog)
    return native_metadata_diagnostics(
        project=inputs.project,
        profile=inputs.profile,
        resource_sql_analysis=inputs.resource_sql_analysis,
        catalog=catalog.native,
    )


def _family_counts(outcome: Any) -> Counter[str]:
    counts: Counter[str] = Counter()
    for function_rows, reference_rows in outcome[1]:
        counts.update(f"function {row[0]}" for row in function_rows)
        counts.update(f"reference {row[0]}" for row in reference_rows)
    counts.update(f"source {row[0]}" for _, row in outcome[2])
    counts.update(f"sql_test {row[0]}" for _, row, _ in outcome[3])
    return counts


def record_metadata_families(*, monkeypatch: pytest.MonkeyPatch) -> Counter[str]:
    """Count native metadata runs, deferrals and errors by family and code."""

    counts: Counter[str] = Counter()
    check: Callable[..., Any] = native_module.check_semantic_metadata_rows

    def counted(*arguments: Any) -> Any:
        outcome: Any = check(*arguments)
        counts[("native", "deferred")[outcome[0] is not None]] += 1
        counts.update(_family_counts(outcome))
        return outcome

    monkeypatch.setattr(native_module, "check_semantic_metadata_rows", counted)
    return counts
