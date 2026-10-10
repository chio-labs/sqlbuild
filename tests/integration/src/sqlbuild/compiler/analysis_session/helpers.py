from __future__ import annotations

import json
import random
from collections import Counter
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field, replace
from itertools import chain
from pathlib import Path
from typing import Any, cast

import pytest

import sqlbuild._native as native_module
import sqlbuild.compiler.analysis_session.classes.native_model_analysis as native_model_analysis
import sqlbuild.compiler.compile._helpers.assembly.project as project_assembly
import sqlbuild.compiler.compile._helpers.native_stages.assembly as native_stage_assembly
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.cli.entry.main.entry import main
from sqlbuild.compiler.analysis_session.main._analyze_native_model_sql import (
    analyze_native_model_sql,
)
from sqlbuild.compiler.analysis_session.main._infer_native_expression_source_shapes import (
    infer_native_expression_source_shapes,
)
from sqlbuild.compiler.analysis_session.main._prove_native_dynamic_contracts import (
    prove_native_dynamic_contracts,
)
from sqlbuild.compiler.analysis_session.models import (
    NativeModelAnalyses,
    NativeModelAnalysisRequest,
    NativePivotTables,
)
from sqlbuild.compiler.compile._helpers.analysis.cache import build_analysis_cache_context
from sqlbuild.compiler.compile._helpers.analysis.pivot_requests import (
    model_dynamic_families,
    model_pivot_sql,
)
from sqlbuild.compiler.compile._helpers.analysis.syntax_checks import model_placeholders
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import (
    cursor_intrinsics_analysis_sql,
)
from sqlbuild.compiler.compile.classes.python_model_analysis import PythonModelAnalysis
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import (
    AnalysisCacheContext,
    CompactLineageFacts,
    CompileAdapterContext,
    CompiledLineageColumnFact,
    CompiledModel,
    CompileProjectInputs,
    DynamicColumnContractProof,
    InferredColumn,
    ModelSqlAnalysis,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.lineage.types import ColumnLineageMode, InferredNullability
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily
from sqlbuild.sql_values.types import CollectionRendering
from tests.integration.src.sqlbuild.compiler.golden_views import GoldenEntry, golden_entry

_PROJECT_TOML: str = (
    'name = "orders_analysis"\nadapter = "duckdb"\n\n[connection]\ndatabase = "orders.duckdb"\n'
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
  - name: raw_customers
    description: Customers feed.
    expression: >-
      (SELECT 10 AS customer_id, 'Ada' AS Customer_Name, 'east' AS region)
  - name: raw_payments
    description: Typed payments feed.
    expression: >-
      (SELECT 10 AS customer_id, 'east' AS region, CAST(5 AS DECIMAL(10, 2)) AS amount)
    columns:
      - name: customer_id
        type: INTEGER
      - name: region
        type: VARCHAR
      - name: amount
        type: DECIMAL(10, 2)
  - name: raw_events
    description: Untyped events feed.
    columns:
      - name: event_id
      - name: order_id
      - name: kind
"""
_INITIAL_RELATIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('__source("raw_orders")', ("order_id", "customer_id", "amount", "status")),
    ('__source("raw_customers")', ("customer_id", "Customer_Name", "region")),
    ('__source("raw_events")', ("event_id", "order_id", "kind")),
)
_ADAPTER_CONTEXT: CompileAdapterContext = CompileAdapterContext(
    value_renderer=DuckDbAdapter(),
    collection_rendering=CollectionRendering.VALUE_LIST,
    python_functions_inherit_default_namespace=True,
    sql_lexical_syntax=DuckDbAdapter.sql_lexical_syntax,
)
_DUCKDB_PROFILE: ExpressionInferenceProfile = ExpressionInferenceProfile(
    sql_analysis_dialect="duckdb"
)
_PIVOT_HEADER: str = """MODEL (
  description "Order amounts pivoted by status",
  contract enforced,
  materialized table,
  columns (customer_id (type INTEGER)),
  dynamic_columns (
    status_amounts (
      pivot_column {pivot},
      value_column {value},
      aggregate {aggregate},
      type DOUBLE
    )
  ),
);

"""
_PIVOT_BODIES: tuple[str, ...] = (
    'PIVOT __source("raw_orders")\nON status\nUSING {aggregate}(amount)\nGROUP BY customer_id',
    'PIVOT __source("raw_orders")\nON status\nUSING {aggregate}(CAST(amount AS DECIMAL(12, 2)))',
    "WITH base AS (\n  SELECT customer_id, status, CAST(amount AS DOUBLE) AS amount\n"
    '  FROM __source("raw_orders")\n)\nSELECT * FROM base\n'
    "PIVOT ({aggregate}(amount) FOR status IN (ANY ORDER BY status))",
    'WITH base AS (\n  SELECT * FROM __source("raw_orders")\n),\npivoted AS (\n'
    "  PIVOT base ON status USING {aggregate}(amount) GROUP BY customer_id\n)\n"
    "SELECT * FROM pivoted",
    "PIVOT __source(\"raw_orders\")\nON status IN ('placed', 'shipped')\n"
    "USING {aggregate}(amount)\nGROUP BY customer_id",
    'PIVOT __source("raw_events")\nON kind\nUSING {aggregate}(order_id)\nGROUP BY event_id',
    'SELECT * FROM __source("raw_orders") o\nJOIN __source("raw_customers") c USING (customer_id)',
)
_PIVOT_AGGREGATES: tuple[str, ...] = ("MAX", "MIN", "ANY_VALUE", "SUM")
_TYPED_PIVOT: str = (
    _PIVOT_HEADER.format(pivot="status", value="amount", aggregate="MAX")
    + _PIVOT_BODIES[0].format(aggregate="MAX")
    + "\n"
)
_TYPED_PIVOT_PASSTHROUGH: str = (
    _PIVOT_HEADER.format(pivot="status", value="amount", aggregate="MAX")
    + 'SELECT * FROM __ref("status_amounts")\n'
)
_ADAPTER_RULE_SQL: dict[str, tuple[str, str]] = {
    "adapter_rules_cte": (
        "  contract enforced,\n",
        "WITH base AS (\n  SELECT customer_id, IFF(region IS NULL, 'a', NULL) AS maybe_label,\n"
        "    IFF(region IS NULL, 'a', 'b') AS label, UPPER(region) AS upper_region,\n"
        "    LOWER('X') AS lower_constant, SPLIT_PART(region, '_', 1) AS region_prefix,\n"
        "    REPLACE(region, '_', '-') AS dashed_region\n"
        '  FROM __source("raw_payments")\n)\n'
        "SELECT customer_id, maybe_label, label, upper_region, lower_constant, region_prefix,\n"
        "  dashed_region\nFROM base",
    ),
    "adapter_rules_untyped_cte": (
        "  contract enforced,\n",
        'WITH base AS (SELECT event_id, kind FROM __source("raw_events"))\n'
        "SELECT event_id, IFF(kind IS NULL, 'a', NULL) AS maybe_label, UPPER(kind) AS upper_kind,\n"
        "  LOWER('X') AS lower_constant, SPLIT_PART(kind, '_', 1) AS kind_prefix\nFROM base",
    ),
    "adapter_rules_staging": (
        "",
        "SELECT event_id, IFF(kind IS NULL, 'a', NULL) AS maybe_label, UPPER(kind) AS upper_kind,\n"
        "  LISTAGG(kind) AS kinds, TO_DATE('2026-01-01') AS start_date\n"
        'FROM __source("raw_events")\nGROUP BY event_id, kind',
    ),
    "long_s_cte": (
        "  contract enforced,\n",
        "WITH base AS (SELECT event_id, 'ſplit_part' AS label FROM __source(\"raw_events\"))\n"
        "SELECT event_id, label FROM base",
    ),
    "long_s_staging": (
        "",
        "SELECT event_id, 'ſplit_part' AS label, kind FROM __source(\"raw_events\")",
    ),
    "dotless_i_staging": (
        "",
        "SELECT event_id, 'lıstagg' AS label FROM __source(\"raw_events\")",
    ),
    "umlaut_cte": (
        "  contract enforced,\n",
        "WITH base AS (SELECT event_id, 'grüße' AS label FROM __source(\"raw_events\"))\n"
        "SELECT event_id, label FROM base",
    ),
}
ADAPTER_RULE_MODELS: dict[str, str] = {
    f"models/adapter_rules/{name}.sql": (
        f'MODEL (\n  description "Adapter rule model {name}",\n{header});\n\n{sql}\n'
    )
    for name, (header, sql) in _ADAPTER_RULE_SQL.items()
}
_CONTRACT_CTE_MODELS: dict[str, str] = {
    "models/marts/payments_by_customer.sql": (
        'MODEL (\n  description "Payments passed through a CTE",\n  contract enforced,\n'
        "  columns (customer_id (type INTEGER), region (type VARCHAR)),\n);\n\n"
        'WITH base AS (SELECT customer_id, region FROM __source("raw_payments"))\n'
        "SELECT customer_id, region FROM base\n"
    ),
    "models/marts/payment_totals.sql": (
        'MODEL (\n  description "Payment totals aggregated in a CTE",\n  contract enforced,\n'
        "  columns (total_amount (type DECIMAL(38, 2)), region (type VARCHAR)),\n);\n\n"
        "WITH base AS (\n  SELECT SUM(amount) AS total_amount, region\n"
        '  FROM __source("raw_payments")\n  GROUP BY region\n)\n'
        "SELECT total_amount, region FROM base\n"
    ),
}


def _pivot_models(rng: random.Random) -> dict[str, str]:
    """A typed pivot every passthrough reads, and seeded pivot shapes proven or refused."""

    files: dict[str, str] = {
        "models/marts/status_amounts.sql": _TYPED_PIVOT,
        "models/marts/status_passthrough.sql": _TYPED_PIVOT_PASSTHROUGH,
    }
    for index, body in enumerate(rng.sample(_PIVOT_BODIES, k=4)):
        aggregate: str = rng.choice(_PIVOT_AGGREGATES)
        header: str = _PIVOT_HEADER.format(
            pivot=rng.choice(("status", "status", "kind")),
            value=rng.choice(("amount", "amount", "order_id")),
            aggregate=aggregate,
        )
        files[f"models/marts/pivot_{index}.sql"] = header + body.format(aggregate=aggregate) + "\n"
    return files


type _Relation = tuple[str, tuple[str, ...]]
type _Template = Callable[[random.Random, list[_Relation]], tuple[str, str, tuple[str, ...]]]


def _star(rng: random.Random, inputs: list[_Relation]) -> tuple[str, str, tuple[str, ...]]:
    relation, columns = inputs[0]
    return "", f"SELECT * FROM {relation}", columns


def _qualified_star(
    rng: random.Random, inputs: list[_Relation]
) -> tuple[str, str, tuple[str, ...]]:
    (left, left_columns), (right, right_columns) = inputs[0], inputs[-1]
    extra: str = rng.choice(right_columns)
    sql: str = (
        f"SELECT a.*, b.{extra} AS joined_{extra.lower()}, 1 AS flag\n"
        f"FROM {left} a\nJOIN {right} b ON TRUE"
    )
    return "", sql, (*left_columns, f"joined_{extra.lower()}", "flag")


def _nested_ctes(rng: random.Random, inputs: list[_Relation]) -> tuple[str, str, tuple[str, ...]]:
    relation, columns = inputs[0]
    picked: list[str] = rng.sample(list(columns), k=min(2, len(columns)))
    sql: str = (
        f"WITH base AS (\n  SELECT {', '.join(picked)} FROM {relation}\n),\n"
        "layered AS (\n  SELECT * FROM base\n)\n"
        f"SELECT {picked[0]} AS key_value, COUNT(*) AS row_count\nFROM layered\nGROUP BY 1"
    )
    return "", sql, ("key_value", "row_count")


def _set_operation(rng: random.Random, inputs: list[_Relation]) -> tuple[str, str, tuple[str, ...]]:
    (left, left_columns), (right, right_columns) = inputs[0], inputs[-1]
    operator: str = rng.choice(("UNION ALL", "UNION", "EXCEPT", "INTERSECT"))
    sql: str = (
        f"SELECT {left_columns[0]} AS shared_key, 'left' AS side FROM {left}\n"
        f"{operator}\nSELECT {right_columns[0]}, 'right' FROM {right}"
    )
    return "", sql, ("shared_key", "side")


def _expressions(rng: random.Random, inputs: list[_Relation]) -> tuple[str, str, tuple[str, ...]]:
    relation, columns = inputs[0]
    first, last = columns[0], columns[-1]
    sql: str = (
        f"SELECT CAST({first} AS VARCHAR) AS as_text, {first} IS NULL AS is_missing,\n"
        f"  COALESCE({first}, {last}) AS filled, {last} AS passthrough,\n"
        f"  ROW_NUMBER() OVER (PARTITION BY {last} ORDER BY {first}) AS position\n"
        f"FROM {relation}\nWHERE {first} IS NOT NULL"
    )
    return "", sql, ("as_text", "is_missing", "filled", "passthrough", "position")


def _aggregate(rng: random.Random, inputs: list[_Relation]) -> tuple[str, str, tuple[str, ...]]:
    relation, columns = inputs[0]
    column: str = rng.choice(columns)
    sql: str = (
        f"SELECT {column} AS group_key, COUNT(*) AS row_count, MAX({columns[-1]}) AS latest\n"
        f"FROM {relation}\nGROUP BY 1"
    )
    return "", sql, ("group_key", "row_count", "latest")


def _quoted(rng: random.Random, inputs: list[_Relation]) -> tuple[str, str, tuple[str, ...]]:
    relation, columns = inputs[0]
    column: str = rng.choice(columns)
    sql: str = (
        f'SELECT "{column}" AS "Mixed_Case", UPPER(CAST(Src.{column.upper()} AS VARCHAR)) AS Up\n'
        f"FROM {relation} AS Src"
    )
    return "", sql, ("Mixed_Case", "Up")


def _contract(rng: random.Random, inputs: list[_Relation]) -> tuple[str, str, tuple[str, ...]]:
    relation, columns = inputs[0]
    sql: str = (
        f"SELECT CAST({columns[0]} AS INTEGER) AS contract_key,\n"
        f"  CAST({columns[-1]} AS VARCHAR) AS contract_label\nFROM {relation}"
    )
    header: str = (
        "  contract enforced,\n"
        "  columns (contract_key (type INTEGER), contract_label (type VARCHAR)),\n"
    )
    return header, sql, ("contract_key", "contract_label")


_CTE_CONTRACT_BODIES: tuple[str, ...] = (
    "WITH base AS (\n  SELECT {a}, {b} FROM {left}\n)\nSELECT {a}, {b} FROM base",
    "WITH base AS (\n  SELECT CAST({a} AS VARCHAR(12)) AS label, COALESCE({b}, {a}) AS filled,\n"
    "    'fixed' AS tag, CAST(1.5 AS DECIMAL(10, 2)) AS ratio, {a} IS NULL AS missing\n"
    "  FROM {left}\n  WHERE {a} IS NOT NULL\n)\n"
    "SELECT label, filled, tag, ratio, missing FROM base",
    "WITH base AS (\n  SELECT CASE WHEN {a} IS NULL THEN 'none' ELSE 'some' END AS state,\n"
    "    UPPER(CAST({b} AS VARCHAR)) AS upper_b, CAST({a} AS TEXT) || '-x' AS joined\n"
    "  FROM {left}\n)\nSELECT state, upper_b, joined FROM base",
    "WITH unioned AS (\n  SELECT {a} AS shared FROM {left}\n  UNION ALL\n"
    "  SELECT {c} FROM {right}\n)\nSELECT shared FROM unioned",
    "WITH base AS (\n  SELECT * EXCLUDE ({a}) FROM {left}\n)\nSELECT {b} FROM base",
    "WITH lhs AS (\n  SELECT {a}, {b} FROM {left}\n),\nrhs AS (\n  SELECT {c} FROM {right}\n)\n"
    "SELECT l.{a}, r.{c}\nFROM lhs l\nLEFT JOIN rhs r ON l.{a} = r.{c}",
    "WITH outer_cte AS (\n  WITH inner_cte AS (SELECT {a}, {b} FROM {left})\n"
    "  SELECT {a}, {b} FROM inner_cte\n)\nSELECT {a}, {b} FROM outer_cte",
    "WITH base AS (\n  SELECT {a}, NULLIF({b}, {b}) AS cleared, MAX({b}) AS latest FROM {left}\n"
    "  GROUP BY {a}\n)\nSELECT {a}, cleared, latest FROM base WHERE {a} IS NOT NULL",
)


def _cte_contract(rng: random.Random, inputs: list[_Relation]) -> tuple[str, str, tuple[str, ...]]:
    (left, left_columns), (right, right_columns) = inputs[0], inputs[-1]
    first, second = rng.sample(list(left_columns), k=2)
    body: str = rng.choice(_CTE_CONTRACT_BODIES)
    sql: str = body.format(a=first, b=second, c=right_columns[0], left=left, right=right)
    return "  contract enforced,\n", sql, (first, second)


def _unknown_column(
    rng: random.Random, inputs: list[_Relation]
) -> tuple[str, str, tuple[str, ...]]:
    relation, columns = inputs[0]
    sql: str = f"SELECT {columns[0]}, missing_column FROM {relation}"
    return "", sql, (columns[0], "missing_column")


def _cast_constant(rng: random.Random, inputs: list[_Relation]) -> tuple[str, str, tuple[str, ...]]:
    relation, columns = inputs[0]
    column: str = rng.choice(columns)
    sql: str = f"SELECT {column}, CAST(NULL AS INT) AS missing_id\nFROM {relation}"
    return "", sql, (column, "missing_id")


def _subquery(rng: random.Random, inputs: list[_Relation]) -> tuple[str, str, tuple[str, ...]]:
    relation, columns = inputs[0]
    column: str = rng.choice(columns)
    sql: str = f"SELECT s.{column}, s.* FROM (SELECT * FROM {relation}) s"
    return "", sql, columns


_TEMPLATES: tuple[_Template, ...] = (
    _star,
    _qualified_star,
    _nested_ctes,
    _set_operation,
    _expressions,
    _aggregate,
    _quoted,
    _contract,
    _cte_contract,
    _unknown_column,
    _subquery,
    _cast_constant,
)


def pivot_project_files() -> dict[str, str]:
    """A typed pivot with its passthrough and one plain model, for selective assembly."""

    return {
        "sqlbuild_project.toml": _PROJECT_TOML,
        "sources/raw.yml": _SOURCES,
        "models/marts/status_amounts.sql": _TYPED_PIVOT,
        "models/marts/status_passthrough.sql": _TYPED_PIVOT_PASSTHROUGH,
        "models/staging/orders_list.sql": (
            'MODEL (description "Order ids");\n\nSELECT order_id FROM __source("raw_orders")\n'
        ),
    }


@dataclass
class NativePivotProofs:
    """Every native pivot proof assembly took, and how many a finished session proved."""

    proofs: list[DynamicColumnContractProof | None] = field(default_factory=list)
    session_proofs: int = 0


def native_pivot_proofs(*, monkeypatch: pytest.MonkeyPatch) -> NativePivotProofs:
    """Record every batch of native pivot proofs assembly takes."""

    recorded_proofs: NativePivotProofs = NativePivotProofs()
    native_proofs: Callable[..., tuple[DynamicColumnContractProof | None, ...]] = (
        native_stage_assembly.prove_native_dynamic_contracts
    )

    def recorded(**keywords: Any) -> tuple[DynamicColumnContractProof | None, ...]:
        proofs: tuple[DynamicColumnContractProof | None, ...] = native_proofs(**keywords)
        recorded_proofs.proofs.extend(proofs)
        proven: int = sum(proof is not None for proof in proofs)
        recorded_proofs.session_proofs += proven * (keywords["session"] is not None)
        return proofs

    monkeypatch.setattr(native_stage_assembly, "prove_native_dynamic_contracts", recorded)
    return recorded_proofs


def generated_analysis_files(*, rng: random.Random, model_count: int) -> dict[str, str]:
    """Sources (typed, inferred and untyped), a pivot and models drawing on every template."""

    files: dict[str, str] = {
        "sqlbuild_project.toml": _PROJECT_TOML,
        "sources/raw.yml": _SOURCES,
        **_pivot_models(rng),
        **_CONTRACT_CTE_MODELS,
    }
    relations: list[_Relation] = list(_INITIAL_RELATIONS)
    for index in range(model_count):
        template: _Template = _TEMPLATES[index % len(_TEMPLATES)]
        header, sql, columns = template(rng, rng.sample(relations, k=2))
        name: str = f"orders_model_{index}"
        files[f"models/layer_{index % 3}/{name}.sql"] = (
            f'MODEL (\n  description "Generated orders model {index}",\n{header});\n\n{sql}\n'
        )
        relations.append((f'__ref("{name}")', columns))
    return files


def shared_analysis_files(
    *, regions: tuple[str, ...], inexact_regions: tuple[str, ...]
) -> dict[str, str]:
    """Equal regional models and rollups, missing-column readers and one unshared summary."""

    regional: dict[str, str] = {
        f"models/staging/orders_{region}.sql": (
            f'MODEL (description "Orders in {region}");\n\n'
            'SELECT order_id, customer_id, amount FROM __source("raw_orders")\n'
        )
        for region in regions
    }
    rollups: dict[str, str] = {
        f"models/marts/totals_{region}.sql": (
            f'MODEL (description "Customer totals in {region}");\n\n'
            "SELECT customer_id, SUM(amount) AS total_amount\n"
            f'FROM __ref("orders_{region}")\nGROUP BY customer_id\n'
        )
        for region in regions
    }
    inexact: dict[str, str] = {
        f"models/marts/missing_{region}.sql": (
            f'MODEL (description "Orders in {region} with an unknown column");\n\n'
            f'SELECT customer_id, missing_column FROM __ref("orders_{region}")\n'
        )
        for region in inexact_regions
    }
    return {
        "sqlbuild_project.toml": _PROJECT_TOML,
        "sources/raw.yml": _SOURCES,
        **regional,
        **rollups,
        **inexact,
        "models/marts/orders_summary.sql": (
            'MODEL (description "Order count");\n\n'
            f'SELECT COUNT(*) AS order_count FROM __ref("orders_{regions[0]}")\n'
        ),
    }


def started_sessions(*, monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Record every native session started; return the list they are appended to."""

    started: list[Any] = []
    original: Callable[..., Any] = native_module.start_model_analysis_session

    def start(catalog: object, request: tuple[object, ...], *options: Any) -> Any:
        started.append(original(catalog, request, *options))
        return started[-1]

    monkeypatch.setattr(native_module, "start_model_analysis_session", start)
    return started


def compile_inputs(*, project_dir: Path, files: dict[str, str]) -> CompileProjectInputs:
    """Write a project and attach its compile inputs with the DuckDB compile context."""

    for relative_path, contents in files.items():
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")
    return build_compile_inputs(
        discovered_inputs=discover_project_inputs(project_dir=project_dir),
        adapter_context=_ADAPTER_CONTEXT,
        run_id="integration_run",
    )


def compiled_project_view(
    *,
    project_dir: Path,
    files: dict[str, str],
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, object, object, dict[str, str]]:
    """Compile a written project through the CLI: exit code, report, manifest nodes, SQL files."""

    for relative_path, contents in files.items():
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")
    _ = capsys.readouterr()
    code: int = main(["--project-dir", str(project_dir), "compile", "--json", "--manifest"])
    report: dict[str, object] = json.loads(capsys.readouterr().out)
    manifest: dict[str, object] = json.loads(
        (project_dir / "target" / "manifest.json").read_text(encoding="utf-8")
    )
    compiled: Path = project_dir / "target" / "compiled"
    _ = report.pop("compile_timings")
    _ = manifest.pop("metadata")
    return (
        code,
        report,
        manifest,
        {
            path.relative_to(compiled).as_posix(): path.read_text(encoding="utf-8")
            for path in sorted(compiled.rglob("*.sql"))
        },
    )


@dataclass
class NativeAnalysisRuns:
    """Each native analysis seam call's uncached, cold-cached and warm-cached views."""

    names: list[object] = field(default_factory=list)
    uncached: list[object] = field(default_factory=list)
    cached: list[object] = field(default_factory=list)
    analysed_models: int = 0
    expression_shapes: int = 0
    pivot_proofs: int = 0
    standalone_proofs: int = 0
    session_proofs: int = 0
    proven_pivots: int = 0
    native_enrichments: int = 0
    native_column_objects: int = 0
    native_column_values: int = 0
    golden: list[GoldenEntry] = field(default_factory=list)


def analyse_natively(
    *,
    inputs: CompileProjectInputs,
    inference_profile: ExpressionInferenceProfile,
    lineage_mode: ColumnLineageMode,
    runs: NativeAnalysisRuns,
    cache_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assemble `inputs`, analysing each model batch natively uncached, cold-cached and warm.

    Every analysis, catalog change, session and standalone dynamic pivot proof, and expression
    shape must not depend on the analysis store, on the session, or on Python's shape inference.
    `runs.golden` gathers the entries the Python oracle recorded for the same seam calls.
    """

    original_analysis: Callable[..., tuple[dict[str, ModelSqlAnalysis], Any]] = (
        native_stage_assembly.analyze_model_sql
    )

    def analysed_three_ways(
        request: NativeModelAnalysisRequest,
    ) -> tuple[dict[str, ModelSqlAnalysis], Any]:
        profile: ExpressionInferenceProfile = request.inference_profile
        cache: AnalysisCacheContext | None = build_analysis_cache_context(
            root=cache_root, inference_profile=profile, allow_compact_analysis=True
        )
        cached_views: list[object] = []
        for _ in range(2):
            catalog: Any = cast(Any, profile.binding_catalog).with_relations({})
            cached: NativeModelAnalyses = analyze_native_model_sql(
                request=replace(
                    request,
                    analysis_cache=cache,
                    inference_profile=replace(profile, binding_catalog=catalog),
                )
            )
            cached_views.append((_analysis_views(cached.analyses), _catalog_view(catalog)))
        analyses, session = original_analysis(replace(request, analysis_cache=None))
        uncached_view: object = (_analysis_views(analyses), _catalog_view(profile.binding_catalog))
        columns: list[InferredColumn] = list(
            chain.from_iterable(map(_native_columns, analyses.values()))
        )
        runs.native_column_objects += len(set(map(id, columns)))
        runs.native_column_values += len(set(columns))
        runs.analysed_models += len(analyses)
        runs.golden.append(golden_entry("models", _analysis_views(analyses)))
        runs.golden.append(golden_entry("catalog", _catalog_view(profile.binding_catalog)))
        for index, view in enumerate(cached_views):
            _append(runs, f"model analyses, cached run {index}", uncached_view, view)
        _compare_proofs(request=request, analyses=analyses, session=session, runs=runs)
        return analyses, session

    def recorded_shapes(
        *, expressions: tuple[str, ...], profile: ExpressionInferenceProfile
    ) -> tuple[dict[str, str] | None, ...]:
        catalog: Any = cast(Any, profile.binding_catalog)
        native: tuple[dict[str, str] | None, ...] = infer_native_expression_source_shapes(
            expressions=expressions, profile=profile
        )
        runs.expression_shapes += sum(shape is not None for shape in native)
        runs.golden.append(golden_entry("shapes", (native, catalog.expression_shapes)))
        return native

    native_lineage_facts: Callable[..., tuple[CompiledLineageColumnFact, ...]] = (
        native_model_analysis.lineage_facts
    )

    def counted_native_enrichment(rows: list[Any]) -> tuple[CompiledLineageColumnFact, ...]:
        runs.native_enrichments += 1
        return native_lineage_facts(rows)

    assembled_model: Callable[..., CompiledModel] = project_assembly._assemble_compiled_model

    def recorded_model(*arguments: Any, **keywords: Any) -> CompiledModel:
        model: CompiledModel = assembled_model(*arguments, **keywords)
        runs.golden.append(golden_entry("proof", model.dynamic_column_contract))
        return model

    with monkeypatch.context() as patch:
        patch.setattr(native_model_analysis, "lineage_facts", counted_native_enrichment)
        patch.setattr(project_assembly, "_assemble_compiled_model", recorded_model)
        patch.setattr(project_assembly, "analyze_model_sql", analysed_three_ways)
        patch.setattr(project_assembly, "expression_source_shapes_by_engine", recorded_shapes)
        with suppress(CompileInputError):
            _ = project_assembly.assemble_compiled_project(
                inputs=inputs,
                inference_profile=replace(inference_profile),
                column_lineage_mode=lineage_mode,
            )


def record_python_model_analyses(*, monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Record every Python model analysis assembly runs; return the list they are appended to."""

    calls: list[object] = []
    original: Callable[..., Any] = project_assembly.analyze_columns_and_lineage_with_polyglot

    def recorded(**keywords: Any) -> Any:
        calls.append(keywords.get("query_sql"))
        return original(**keywords)

    monkeypatch.setattr(project_assembly, "analyze_columns_and_lineage_with_polyglot", recorded)
    return calls


def duplicate_analysed_model_names(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Name every analysed model after the first, an invariant discovery guarantees (D007)."""

    original: Callable[[PythonModelAnalysis], list[tuple[object, ...]]] = (
        PythonModelAnalysis.model_rows
    )

    def renamed(analysis: PythonModelAnalysis) -> list[tuple[object, ...]]:
        rows: list[tuple[object, ...]] = original(analysis)
        return [(rows[0][0], *row[1:]) for row in rows]

    monkeypatch.setattr(PythonModelAnalysis, "model_rows", renamed)


def custom_nullability_rule(arguments: tuple[InferredNullability, ...]) -> InferredNullability:
    """An adapter rule SQLBuild does not ship, so native analysis calls it back."""

    return InferredNullability.NULLABLE


def analysis_request(
    *,
    inputs: CompileProjectInputs,
    monkeypatch: pytest.MonkeyPatch,
    inference_profile: ExpressionInferenceProfile = _DUCKDB_PROFILE,
) -> NativeModelAnalysisRequest:
    """The native request the model analysis seam builds while assembling `inputs`."""

    requests: list[NativeModelAnalysisRequest] = []

    def captured(request: NativeModelAnalysisRequest) -> tuple[dict[str, ModelSqlAnalysis], None]:
        requests.append(request)
        return {}, None

    with monkeypatch.context() as patch, suppress(CompileInputError):
        patch.setattr(project_assembly, "analyze_model_sql", captured)
        _ = project_assembly.assemble_compiled_project(
            inputs=inputs,
            inference_profile=inference_profile,
        )
    return requests[0]


def deferral_kinds(record_dir: Path) -> Counter[str]:
    """Count the `site:kind` deferral records below `record_dir`."""

    lines: list[str] = list(
        chain.from_iterable(
            path.read_text("utf-8").splitlines()
            for path in sorted(record_dir.glob("analysis-deferrals-*.jsonl"))
        )
    )
    records: list[dict[str, str]] = [json.loads(line) for line in lines]
    return Counter(f"{record['site']}:{record['kind']}" for record in records)


def _native_columns(analysis: ModelSqlAnalysis) -> tuple[InferredColumn, ...]:
    return analysis.polyglot_analysis.columns or ()


def _compare_proofs(
    *,
    request: NativeModelAnalysisRequest,
    analyses: dict[str, ModelSqlAnalysis],
    session: Any,
    runs: NativeAnalysisRuns,
) -> None:
    """Each analysed pivot model's proof, proven again in the session and standalone."""

    tables: NativePivotTables = NativePivotTables(
        dialect=request.inference_profile.sql_analysis_dialect,
        column_types_by_table=request.column_types_by_table,
        authoritative_column_types_by_table=request.complete_binding_schemas,
        column_nullability_by_table=request.column_nullability_by_table,
        dynamic_families_by_table=request.dynamic_families_by_table,
    )
    for model_input in request.model_inputs:
        families: tuple[SchemaDynamicColumnFamily, ...] = model_dynamic_families(model_input)
        analysis: ModelSqlAnalysis | None = analyses.get(model_input.model_file.file_path.stem)
        if not families or analysis is None:
            continue
        models: tuple[tuple[str, tuple[SchemaDynamicColumnFamily, ...]], ...] = (
            (
                model_pivot_sql(
                    query_sql=cursor_intrinsics_analysis_sql(
                        sql=model_input.query_sql,
                        cursor_type=model_input.config.values.get("cursor_type"),
                    ),
                    placeholders=model_placeholders(model_input),
                ),
                families,
            ),
        )
        proof: DynamicColumnContractProof | None = analysis.dynamic_column_contract
        standalone: DynamicColumnContractProof | None = prove_native_dynamic_contracts(
            session=None, tables=tables, models=models
        )[0]
        in_session: DynamicColumnContractProof | None = prove_native_dynamic_contracts(
            session=session, tables=tables, models=models
        )[0]
        runs.pivot_proofs += proof is not None
        runs.proven_pivots += proof is not None and proof.output_proven
        runs.standalone_proofs += standalone is not None
        runs.session_proofs += in_session is not None
        _append(runs, "standalone dynamic pivot proof", proof, standalone)
        _append(runs, "session dynamic pivot proof", proof, in_session)


def _append(runs: NativeAnalysisRuns, name: str, uncached: object, cached: object) -> None:
    runs.names.append(name)
    runs.uncached.append(uncached)
    runs.cached.append(cached)


def _analysis_views(analyses: dict[str, ModelSqlAnalysis]) -> object:
    return {
        name: (
            analysis.polyglot_analysis.analysis_succeeded,
            analysis.polyglot_analysis.columns,
            isinstance(analysis.polyglot_analysis.lineage_columns, CompactLineageFacts),
            tuple(analysis.polyglot_analysis.lineage_columns),
            analysis.polyglot_analysis.has_star,
            analysis.polyglot_analysis.star_resolved,
            analysis.polyglot_analysis.binding_diagnostics,
            analysis.polyglot_analysis.binding_validated,
            analysis.cleaned_sql,
            analysis.placeholders,
        )
        for name, analysis in analyses.items()
    }


def _catalog_view(catalog: Any) -> tuple[object, ...]:
    return (dict(catalog.schemas), dict(catalog.analysis_shapes))
