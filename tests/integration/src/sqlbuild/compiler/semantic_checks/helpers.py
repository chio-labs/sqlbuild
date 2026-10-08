from __future__ import annotations

import json
import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from itertools import chain
from pathlib import Path
from typing import Any

import pytest

import sqlbuild._native as native_module
import sqlbuild.compiler.compile._helpers.assembly.project as assembly_project
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile._helpers.diagnostics.recovery import (
    complete_semantic_diagnostics,
)
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.semantic_checks.main._complete_native_semantic_diagnostics import (
    complete_native_semantic_diagnostics,
)
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic

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
    *, project_dir: Path, files: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> SemanticInputs:
    """Compile with the Python engine and keep the semantic completion stage's inputs."""

    for relative_path, contents in files.items():
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")
    captured: list[SemanticInputs] = []

    def capture(**arguments: Any) -> CompiledProject:
        captured.append(SemanticInputs(**arguments))
        return complete_semantic_diagnostics(**arguments)

    with monkeypatch.context() as patch:
        patch.setenv(COMPILER_ENGINE_ENV_VAR, "python")
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
    )


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
