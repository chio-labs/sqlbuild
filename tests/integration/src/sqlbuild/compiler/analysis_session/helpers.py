from __future__ import annotations

import json
import random
from collections import Counter
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field, replace
from functools import partial
from itertools import chain
from pathlib import Path
from typing import Any, cast

import pytest

import sqlbuild._native as native_module
import sqlbuild.compiler.analysis_session.classes.native_model_analysis as native_model_analysis
import sqlbuild.compiler.compile._helpers.analysis.compact as compact_analysis
import sqlbuild.compiler.compile._helpers.assembly.project as project_assembly
import sqlbuild.compiler.compile._helpers.native_stages.assembly as native_stage_assembly
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.analysis_session.main._analyze_native_model_sql import (
    analyze_native_model_sql,
)
from sqlbuild.compiler.analysis_session.main._infer_native_expression_source_shapes import (
    infer_native_expression_source_shapes,
)
from sqlbuild.compiler.analysis_session.main._prove_native_dynamic_contract import (
    prove_native_dynamic_contract,
)
from sqlbuild.compiler.analysis_session.models import NativeModelAnalysisRequest
from sqlbuild.compiler.compile._helpers.assembly.semantic_shapes import (
    get_expression_source_shapes,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import (
    CompactLineageFacts,
    CompileAdapterContext,
    CompiledLineageColumnFact,
    CompileProjectInputs,
    DynamicColumnContractProof,
    ModelSqlAnalysis,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily
from sqlbuild.sql_values.types import CollectionRendering

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


_PYTHON_CTE_RECOVERY: Callable[..., Any] = compact_analysis._polyglot_cte_passthrough_facts

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


def native_pivot_proofs(
    *, monkeypatch: pytest.MonkeyPatch
) -> list[DynamicColumnContractProof | None]:
    """Record every standalone native pivot proof assembly takes, failing any wheel pivot proof."""

    proofs: list[DynamicColumnContractProof | None] = []
    native_proof: Callable[..., DynamicColumnContractProof | None] = (
        native_stage_assembly.prove_native_dynamic_contract
    )

    def recorded(**keywords: Any) -> DynamicColumnContractProof | None:
        proofs.append(native_proof(**keywords))
        return proofs[-1]

    python_proof: Callable[..., DynamicColumnContractProof | None] = (
        project_assembly.analyze_dynamic_column_contract
    )

    def wheel_not_expected(**keywords: Any) -> DynamicColumnContractProof | None:
        assert not keywords["families"], "the Python wheel proved a pivot native should prove"
        return python_proof(**keywords)

    monkeypatch.setattr(native_stage_assembly, "prove_native_dynamic_contract", recorded)
    monkeypatch.setattr(project_assembly, "analyze_dynamic_column_contract", wheel_not_expected)
    return proofs


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


@dataclass
class AnalysisParity:
    """Python's and the native session's views of every analysis seam call."""

    names: list[object] = field(default_factory=list)
    python: list[object] = field(default_factory=list)
    native: list[object] = field(default_factory=list)
    analysed_models: int = 0
    expression_shapes: int = 0
    pivot_proofs: int = 0
    cte_recoveries: int = 0
    standalone_proofs: int = 0
    proven_pivots: int = 0
    native_enrichments: int = 0


def compare_analyses(
    *,
    inputs: CompileProjectInputs,
    dialect: str | None,
    parity: AnalysisParity,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assemble `inputs`, analysing every seam call with both engines into `parity`."""

    def models_by_both(
        *,
        python_analysis: partial[dict[str, ModelSqlAnalysis]],
        dynamic_families_by_table: dict[str, tuple[SchemaDynamicColumnFamily, ...]],
    ) -> dict[str, ModelSqlAnalysis]:
        keywords: dict[str, Any] = {**python_analysis.keywords, "analysis_cache": None}
        profile: ExpressionInferenceProfile = keywords["inference_profile"]
        native_catalog: Any = profile.binding_catalog.with_relations({})
        native: dict[str, ModelSqlAnalysis] | None = analyze_native_model_sql(
            request=NativeModelAnalysisRequest(
                **{
                    **keywords,
                    "inference_profile": replace(profile, binding_catalog=native_catalog),
                },
                dynamic_families_by_table=dynamic_families_by_table,
            )
        )
        with monkeypatch.context() as patch:
            patch.setattr(
                compact_analysis,
                "_polyglot_cte_passthrough_facts",
                partial(_counted_cte_recovery, parity=parity),
            )
            python: dict[str, ModelSqlAnalysis] = python_analysis.func(**keywords)
        parity.analysed_models += len(python)
        _append(parity, "model analyses", _analysis_views(python), _analysis_views(native))
        _append(
            parity,
            "catalog",
            _catalog_view(profile.binding_catalog),
            _catalog_view(native_catalog),
        )
        return native or python

    def proofs_by_both(
        *,
        sql_analysis: ModelSqlAnalysis | None,
        python_proof: partial[DynamicColumnContractProof | None],
    ) -> DynamicColumnContractProof | None:
        native: DynamicColumnContractProof | None = getattr(
            sql_analysis, "dynamic_column_contract", None
        )
        python: DynamicColumnContractProof | None = python_proof()
        standalone: DynamicColumnContractProof | None = prove_native_dynamic_contract(
            **python_proof.keywords
        )
        parity.pivot_proofs += native is not None
        parity.proven_pivots += native is not None and native.output_proven
        parity.standalone_proofs += standalone is not None
        _append(parity, "dynamic pivot proof", python, native or python)
        _append(parity, "standalone dynamic pivot proof", python, standalone or python)
        return python

    def shapes_by_both(
        *, expressions: tuple[str, ...], profile: ExpressionInferenceProfile
    ) -> tuple[dict[str, str] | None, ...]:
        catalog: Any = cast(Any, profile.binding_catalog)
        native_catalog: Any = catalog.with_relations({})
        native: tuple[dict[str, str] | None, ...] | None = infer_native_expression_source_shapes(
            expressions=expressions, profile=replace(profile, binding_catalog=native_catalog)
        )
        python: tuple[dict[str, str] | None, ...] = get_expression_source_shapes(
            expressions=expressions, profile=profile
        )
        parity.expression_shapes += sum(shape is not None for shape in python)
        _append(
            parity,
            "expression shapes",
            (python, catalog.expression_shapes),
            (native, native_catalog.expression_shapes),
        )
        return python

    native_lineage_facts: Callable[..., tuple[CompiledLineageColumnFact, ...]] = (
        native_model_analysis.lineage_facts
    )

    def counted_native_enrichment(rows: list[Any]) -> tuple[CompiledLineageColumnFact, ...]:
        parity.native_enrichments += 1
        return native_lineage_facts(rows)

    with monkeypatch.context() as patch:
        patch.setattr(native_model_analysis, "lineage_facts", counted_native_enrichment)
        patch.setattr(project_assembly, "analyze_model_sql_by_engine", models_by_both)
        patch.setattr(project_assembly, "expression_source_shapes_by_engine", shapes_by_both)
        patch.setattr(project_assembly, "dynamic_column_contract_by_engine", proofs_by_both)
        with suppress(CompileInputError):
            _ = project_assembly.assemble_compiled_project(
                inputs=inputs,
                inference_profile=ExpressionInferenceProfile(sql_analysis_dialect=dialect),
            )


def analysis_request(
    *, inputs: CompileProjectInputs, monkeypatch: pytest.MonkeyPatch
) -> NativeModelAnalysisRequest:
    """The native request the model analysis seam builds while assembling `inputs`."""

    requests: list[NativeModelAnalysisRequest] = []

    def captured(
        *,
        python_analysis: partial[dict[str, ModelSqlAnalysis]],
        dynamic_families_by_table: dict[str, tuple[SchemaDynamicColumnFamily, ...]],
    ) -> dict[str, ModelSqlAnalysis]:
        requests.append(
            NativeModelAnalysisRequest(
                **python_analysis.keywords, dynamic_families_by_table=dynamic_families_by_table
            )
        )
        return python_analysis()

    with monkeypatch.context() as patch, suppress(CompileInputError):
        patch.setattr(project_assembly, "analyze_model_sql_by_engine", captured)
        _ = project_assembly.assemble_compiled_project(
            inputs=inputs,
            inference_profile=ExpressionInferenceProfile(sql_analysis_dialect="duckdb"),
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


def _counted_cte_recovery(*, parity: AnalysisParity, **arguments: Any) -> Any:
    recovered: Any = _PYTHON_CTE_RECOVERY(**arguments)
    parity.cte_recoveries += bool(recovered[2])
    return recovered


def _append(parity: AnalysisParity, name: str, python: object, native: object) -> None:
    parity.names.append(name)
    parity.python.append(python)
    parity.native.append(native)


def _analysis_views(analyses: dict[str, ModelSqlAnalysis] | None) -> object:
    return analyses and {
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


class FailingProvideSession:
    """A native session whose answers to deferrals are refused, as a failed session refuses."""

    def __init__(self, session: Any) -> None:
        self._session: Any = session
        self.answered: int = 0
        self.failure: str = "injected session failure"

    def run(self) -> object:
        return self._session.run()

    def provide(self, answers: list[object]) -> bool:
        self.answered += len(answers)
        return False

    def finish(self) -> object:
        return self._session.finish()


def failing_provide_sessions(*, monkeypatch: pytest.MonkeyPatch) -> list[FailingProvideSession]:
    """Make every native session refuse Python's answers; return the sessions started."""

    started: list[FailingProvideSession] = []
    original: Callable[..., Any] = native_module.start_model_analysis_session

    def start(catalog: object, request: tuple[object, ...]) -> FailingProvideSession:
        started.append(FailingProvideSession(original(catalog, request)))
        return started[-1]

    monkeypatch.setattr(native_module, "start_model_analysis_session", start)
    return started
