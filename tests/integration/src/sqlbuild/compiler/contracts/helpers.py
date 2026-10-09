"""Generated contract inputs, and the Python and native contract results they produce."""

from __future__ import annotations

import itertools
import json
import random
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import sqlbuild._native as native_module
from sqlbuild.adapter.contract.types import TablePromotionMode
from sqlbuild.adapter.type_system._helpers.type_normalization import normalize_type
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompilerDiagnostic,
    DynamicColumnContractProof,
    DynamicColumnFamilyProof,
    InferredColumn,
)
from sqlbuild.compiler.contracts.main.promotion_conflicts import promotion_conflict_diagnostics
from sqlbuild.compiler.contracts.main.validate import evaluate_model_contracts
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.planner.types import ContractPolicy, IncrementalMode, MaterializationType
from sqlbuild.spec.contracts.models import (
    SchemaColumn,
    SchemaDynamicColumnFamily,
    SchemaModelEntry,
    SourceLocation,
)
from sqlbuild.spec.contracts.types import ColumnContractMode

_PROJECT_TOML: str = (
    'name = "orders_contracts"\nadapter = "duckdb"\n\n[connection]\ndatabase = "orders.duckdb"\n'
)
_SOURCES: str = """sources:
  - name: raw_orders
    description: Orders feed.
    expression: >-
      (SELECT 1 AS order_id, 10 AS customer_id, CAST(5 AS DOUBLE) AS amount, 'placed' AS status)
    columns:
      - name: order_id
        type: INTEGER
      - name: customer_id
        type: INTEGER
      - name: amount
        type: DOUBLE
      - name: status
        type: VARCHAR
"""
_MODELS: dict[str, str] = {
    "models/staging/stg_orders.sql": (
        'MODEL (\n  description "Staged orders",\n  contract enforced,\n  columns (\n'
        "    order_id (type INTEGER, nullable false),\n    amount (type DOUBLE),\n  ),\n);\n\n"
        'SELECT order_id, customer_id, amount, status FROM __source("raw_orders")\n'
    ),
    "models/marts/customer_totals.sql": (
        'MODEL (\n  description "Totals per customer",\n  columns (\n'
        "    customer_id (type BIGINT),\n    total_amount (type DECIMAL(18, 2)),\n  ),\n);\n\n"
        "SELECT customer_id, SUM(amount) AS total_amount, COUNT(*) AS order_count,\n"
        "  MAX(status) AS last_status\n"
        'FROM __ref("stg_orders")\nGROUP BY customer_id\n'
    ),
    "models/marts/order_flags.sql": (
        'MODEL (\n  description "Order flags",\n);\n\n'
        "SELECT order_id, amount > 10 AS is_large, CAST(NULL AS VARCHAR) AS note,\n"
        "  status AS Status_Label\n"
        'FROM __ref("stg_orders")\n'
    ),
    "models/marts/all_orders.sql": (
        'MODEL (\n  description "Every order column",\n);\n\nSELECT * FROM __ref("stg_orders")\n'
    ),
}
TYPE_POOL: tuple[str | None, ...] = (
    None,
    "INTEGER",
    "INT",
    "int4",
    "BIGINT",
    "INT64",
    "SMALLINT",
    "VARCHAR",
    "VARCHAR(10)",
    "varchar(255)",
    "STRING",
    "TEXT",
    "CHAR(3)",
    "DOUBLE",
    "FLOAT",
    "FLOAT64",
    "REAL",
    "NUMERIC",
    "NUMERIC(10, 2)",
    "DECIMAL(18,2)",
    "NUMBER(38, 0)",
    "BOOLEAN",
    "BOOL",
    "DATE",
    "TIMESTAMP",
    "TIMESTAMP_NTZ",
    "TIMESTAMPTZ",
    "TIMESTAMP WITH TIME ZONE",
    "DATETIME",
    "JSON",
    "VARIANT",
    "STRUCT<a INT>",
    "ARRAY<INT>",
    "INTEGER[]",
    "MAP(VARCHAR, INTEGER)",
    "not a type (",
    "",
)
_OUTPUT_NAMES: list[str] = [
    "order_id",
    "customer_id",
    "amount",
    "status",
    "total_amount",
    "order_count",
    "is_large",
    "note",
    "Status_Label",
    "missing_id",
    "Order_ID",
]
_ENFORCED_MODEL: str = "stg_orders"
_NAMED_SCHEMA_PATH: Path = Path("schemas/orders_schema.sql")
_LIFECYCLE_KEYS: tuple[str, ...] = ("contract", "materialized", "incremental_mode")
_FAMILY_NAMES: tuple[str, ...] = ("amount_*", "Amount_*", "count_*", "label_*")
_REASONS: tuple[str | None, ...] = (None, "", "no supported pivot")
_CONTRACTS: tuple[object, ...] = (
    "enforced",
    ContractPolicy.ENFORCED,
    "none",
    ContractPolicy.NONE,
    "ENFORCED",
    None,
    1,
)
_MATERIALIZATIONS: tuple[object, ...] = (
    MaterializationType.TABLE,
    "table",
    MaterializationType.VIEW,
    MaterializationType.INCREMENTAL,
    "incremental",
    MaterializationType.SNAPSHOT,
    None,
)
_INCREMENTAL_MODES: tuple[object, ...] = (
    IncrementalMode.MICROBATCH,
    "microbatch",
    IncrementalMode.FULL,
    None,
)
_PROMOTION_MODES: tuple[str | None, ...] = (None, "immediate", "staged", "IMMEDIATE", "")
_SETTINGS_FILES: tuple[str, ...] = ("sqlbuild_project.toml", "sqlbuild_local.toml")

type ContractView = tuple[CompilerDiagnostic, ...]


def compiled_contract_project(*, project_dir: Path) -> CompiledProject:
    """Write and compile the base project whose models the generators perturb."""

    files: dict[str, str] = {
        "sqlbuild_project.toml": _PROJECT_TOML,
        "sources/raw.yml": _SOURCES,
        **_MODELS,
    }
    for relative_path, contents in files.items():
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")
    return build_project_graph(
        discovered_inputs=discover_project_inputs(project_dir=project_dir),
        adapter=DuckDbAdapter(),
    ).project


def perturbed_project(*, project: CompiledProject, rng: random.Random) -> CompiledProject:
    """The project with every model's contract inputs replaced by generated ones."""

    return replace(
        project,
        settings=replace(
            project.settings,
            column_contract_mode=rng.choice(tuple(ColumnContractMode)),
            table_promotion_mode=rng.choice(_PROMOTION_MODES),
        ),
        models=tuple(perturbed_model(model=model, rng=rng) for model in project.models),
    )


def perturbed_model(*, model: CompiledModel, rng: random.Random) -> CompiledModel:
    """One model with generated contract config, declared shape, inference and proof."""

    values: dict[str, object] = dict(model.config.values)
    for key in _LIFECYCLE_KEYS:
        _ = values.pop(key, None)
    for key, options in zip(
        _LIFECYCLE_KEYS, (_CONTRACTS, _MATERIALIZATIONS, _INCREMENTAL_MODES), strict=True
    ):
        values.update(rng.choice(({}, *({key: option} for option in options))))
    return replace(
        model,
        config=replace(model.config, values=values),
        schema_entry=rng.choice((None, *(_schema_entry(model=model, rng=rng),) * 9)),
        inferred_columns=rng.choice((None, *(_inferred_columns(rng=rng),) * 9)),
        fast_lineage_has_star=rng.random() < 0.2,
        dynamic_column_contract=rng.choice((None, None, *(_dynamic_proof(rng=rng),) * 5)),
        unchecked_output_columns=frozenset(rng.sample(_OUTPUT_NAMES, k=rng.randint(0, 2))),
    )


def _schema_entry(*, model: CompiledModel, rng: random.Random) -> SchemaModelEntry:
    columns: tuple[SchemaColumn, ...] = tuple(
        SchemaColumn(
            name=name,
            type=rng.choice(TYPE_POOL),
            nullable=rng.choice((None, False, True)),
            location=rng.choice(
                (
                    None,
                    SourceLocation(path=model.relative_path, line=3, column=5),
                    SourceLocation(path=_NAMED_SCHEMA_PATH, line=2, column=3),
                )
            ),
        )
        for name in rng.sample(_OUTPUT_NAMES, k=rng.randint(0, 4))
    )
    families: tuple[SchemaDynamicColumnFamily, ...] = tuple(
        SchemaDynamicColumnFamily(
            name=name,
            pivot_column="status",
            value_column="amount",
            aggregate="sum",
            type=str(rng.choice(TYPE_POOL[1:])),
        )
        for name in rng.sample(_FAMILY_NAMES, k=rng.choice((0, 0, 1, 2)))
    )
    return SchemaModelEntry(
        name=model.name,
        model_schema=rng.choice((None, None, "orders_schema")),
        type_enforcement=rng.choice((None, False, True)),
        columns=columns,
        dynamic_columns=families,
    )


def _inferred_columns(*, rng: random.Random) -> tuple[InferredColumn, ...]:
    return tuple(
        InferredColumn(
            name=name,
            type=rng.choice(TYPE_POOL),
            nullability=rng.choice(tuple(InferredNullability)),
        )
        for name in rng.choices(_OUTPUT_NAMES, k=rng.randint(0, 6))
    )


def _dynamic_proof(*, rng: random.Random) -> DynamicColumnContractProof:
    return DynamicColumnContractProof(
        output_proven=rng.random() < 0.6,
        failure_reason=rng.choice(_REASONS),
        families=tuple(
            DynamicColumnFamilyProof(
                name=rng.choice((name, name.upper(), name.title())),
                inferred_type=rng.choice(TYPE_POOL),
            )
            for name in rng.sample(_FAMILY_NAMES, k=rng.randint(0, 3))
        ),
    )


def contract_views(
    *,
    project: CompiledProject,
    dialect: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ContractView, ContractView]:
    """Python's and the native engine's contract diagnostics for the same project."""

    return (
        _on_engine(
            engine="python",
            monkeypatch=monkeypatch,
            run=lambda: evaluate_model_contracts(project=project, dialect=dialect).diagnostics,
        ),
        _on_engine(
            engine="native-preview",
            monkeypatch=monkeypatch,
            run=lambda: evaluate_model_contracts(project=project, dialect=dialect).diagnostics,
        ),
    )


def promotion_views(
    *,
    project: CompiledProject,
    adapter_default: TablePromotionMode,
    settings_file: str,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ContractView, ContractView]:
    """Python's and the native engine's K011 promotion conflicts for the same project."""

    def run() -> ContractView:
        return promotion_conflict_diagnostics(
            project=project, adapter_default=adapter_default, settings_file=settings_file
        )

    return (
        _on_engine(engine="python", monkeypatch=monkeypatch, run=run),
        _on_engine(engine="native-preview", monkeypatch=monkeypatch, run=run),
    )


def promotion_settings(*, rng: random.Random) -> tuple[TablePromotionMode, str]:
    """A generated adapter default promotion mode and settings file."""

    return rng.choice(tuple(TablePromotionMode)), rng.choice(_SETTINGS_FILES)


def _on_engine(
    *, engine: str, monkeypatch: pytest.MonkeyPatch, run: Callable[[], ContractView]
) -> ContractView:
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, engine)
    normalize_type.cache_clear()
    return run()


def record_native_outcomes(*, monkeypatch: pytest.MonkeyPatch) -> Counter[str]:
    """Count native contract outcomes (`native` or the deferral kind) for the rest of the test."""

    statuses: Counter[str] = Counter()
    evaluate: Callable[..., Sequence[tuple[str | None, list[Any]]]] = (
        native_module.evaluate_native_model_contracts
    )

    def counted(*arguments: Any) -> Sequence[tuple[str | None, list[Any]]]:
        outcomes: Sequence[tuple[str | None, list[Any]]] = evaluate(*arguments)
        statuses.update(
            [("native", str(deferral))[deferral is not None] for deferral, _ in outcomes]
        )
        statuses["native_diagnostics"] += sum(len(rows) for _, rows in outcomes)
        return outcomes

    monkeypatch.setattr(native_module, "evaluate_native_model_contracts", counted)
    return statuses


def record_native_promotion_calls(*, monkeypatch: pytest.MonkeyPatch) -> Counter[str]:
    """Count native promotion conflict calls and the conflicts they return."""

    statuses: Counter[str] = Counter()
    conflicts: Callable[..., list[tuple[int, str, str, str]]] = (
        native_module.native_promotion_conflicts
    )

    def counted(*arguments: Any) -> list[tuple[int, str, str, str]]:
        found: list[tuple[int, str, str, str]] = conflicts(*arguments)
        statuses["calls"] += 1
        statuses["conflicts"] += len(found)
        return found

    monkeypatch.setattr(native_module, "native_promotion_conflicts", counted)
    return statuses


def deferral_records(directory: Path) -> list[dict[str, str]]:
    """Every deferral record written under `directory`, in file order."""

    lines: Iterator[str] = itertools.chain.from_iterable(
        path.read_text(encoding="utf-8").splitlines()
        for path in sorted(directory.glob("analysis-deferrals-*.jsonl"))
    )
    return [json.loads(line) for line in lines]


def with_declared_type(*, project: CompiledProject, declared_type: str) -> CompiledProject:
    """The project with its enforced staging model declaring `declared_type` for every column."""

    by_name: dict[str, CompiledModel] = {model.name: model for model in project.models}
    staging: CompiledModel = by_name[_ENFORCED_MODEL]
    assert staging.schema_entry is not None
    columns: tuple[SchemaColumn, ...] = tuple(
        replace(column, type=declared_type) for column in staging.schema_entry.columns
    )
    by_name[_ENFORCED_MODEL] = replace(
        staging, schema_entry=replace(staging.schema_entry, columns=columns)
    )
    return replace(project, models=tuple(by_name[model.name] for model in project.models))
