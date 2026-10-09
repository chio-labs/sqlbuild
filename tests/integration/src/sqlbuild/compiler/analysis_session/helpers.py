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
import sqlbuild.compiler.compile._helpers.assembly.project as project_assembly
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.analysis_session.main._analyze_native_model_sql import (
    analyze_native_model_sql,
)
from sqlbuild.compiler.analysis_session.main._infer_native_expression_source_shapes import (
    infer_native_expression_source_shapes,
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
    CompileProjectInputs,
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
_PIVOT_MODEL: str = """MODEL (
  description "Order amounts pivoted by status",
  contract enforced,
  materialized table,
  columns (customer_id (type INTEGER)),
  dynamic_columns (
    status_amounts (
      pivot_column status,
      value_column amount,
      aggregate MAX,
      type DOUBLE
    )
  ),
);

PIVOT __source("raw_orders")
ON status
USING MAX(amount)
GROUP BY customer_id
"""

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
    _unknown_column,
    _subquery,
)


def generated_analysis_files(*, rng: random.Random, model_count: int) -> dict[str, str]:
    """Sources (typed, inferred and untyped), a pivot and models drawing on every template."""

    files: dict[str, str] = {
        "sqlbuild_project.toml": _PROJECT_TOML,
        "sources/raw.yml": _SOURCES,
        "models/marts/status_amounts.sql": _PIVOT_MODEL,
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
        python: dict[str, ModelSqlAnalysis] = python_analysis.func(**keywords)
        parity.analysed_models += len(python)
        _append(parity, "model analyses", _analysis_views(python), _analysis_views(native))
        _append(
            parity,
            "catalog",
            _catalog_view(profile.binding_catalog),
            _catalog_view(native_catalog),
        )
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

    with monkeypatch.context() as patch:
        patch.setattr(project_assembly, "analyze_model_sql_by_engine", models_by_both)
        patch.setattr(project_assembly, "expression_source_shapes_by_engine", shapes_by_both)
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
            analysis.dynamic_column_contract,
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
