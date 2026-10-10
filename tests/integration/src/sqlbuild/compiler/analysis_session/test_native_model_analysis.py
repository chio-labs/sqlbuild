"""The native model analysis session equals Python's model analysis on generated projects."""

from __future__ import annotations

import random
from collections import Counter
from itertools import product
from pathlib import Path
from typing import Any

import pytest

import sqlbuild._native as native_module
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.compiler.analysis_session.main._analyze_native_model_sql import (
    analyze_native_model_sql,
)
from sqlbuild.compiler.analysis_session.models import NativeModelAnalysisRequest
from sqlbuild.compiler.compile._helpers.assembly.project import assemble_compiled_project
from sqlbuild.compiler.compile.models import (
    CompiledProject,
    CompileProjectInputs,
)
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.frontier.types import CompilerEngine
from sqlbuild.compiler.lineage.types import ColumnLineageMode, InferredNullability
from sqlbuild.compiler.sql_analysis.constants import ANALYSIS_RECORD_DIR_ENV_VAR
from tests.integration.src.sqlbuild.compiler.analysis_session._test_types import (
    AdapterRuleCallbackTestCase,
    CyclicAnalysisTestCase,
    CyclicCompileTestCase,
    GeneratedAnalysisTestCase,
    InternalFailureTestCase,
    SharedAnalysisTestCase,
    StandalonePivotProofTestCase,
)
from tests.integration.src.sqlbuild.compiler.analysis_session.helpers import (
    ADAPTER_RULE_MODELS,
    NativeAnalysisRuns,
    NativePivotProofs,
    analyse_natively,
    analysis_request,
    compile_inputs,
    compiled_project_view,
    custom_nullability_rule,
    deferral_kinds,
    duplicate_analysed_model_names,
    generated_analysis_files,
    native_pivot_proofs,
    pivot_project_files,
    record_python_model_analyses,
    shared_analysis_files,
    started_sessions,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches

_DIALECT_PROFILES: tuple[ExpressionInferenceProfile, ...] = tuple(
    ExpressionInferenceProfile(sql_analysis_dialect=dialect)
    for dialect in ("duckdb", "postgres", "snowflake", "bigquery")
)
_ADAPTER_PROFILES: tuple[ExpressionInferenceProfile, ...] = (
    SnowflakeAdapter().expression_inference_profile(),
    DuckDbAdapter().expression_inference_profile(),
)
_CUSTOM_RULE_PROFILES: tuple[ExpressionInferenceProfile, ...] = (
    ExpressionInferenceProfile(
        sql_analysis_dialect="duckdb",
        function_nullability_rules={
            **DuckDbAdapter().expression_inference_profile().function_nullability_rules,
            "SUM": custom_nullability_rule,
            "COALESCE": custom_nullability_rule,
        },
    ),
)
_CYCLIC_PROJECT: dict[str, str] = {
    "sqlbuild_project.toml": 'name = "orders_cycle"\nadapter = "duckdb"\n',
    "sources/raw.yml": (
        "sources:\n  - name: raw_orders\n    description: Raw orders.\n    columns:\n"
        "      - name: order_id\n        type: INTEGER\n"
        "      - name: amount\n        type: DOUBLE\n"
    ),
    "models/orders.sql": (
        'MODEL (description "Orders");\n\nSELECT o.order_id, o.amount, r.refund\n'
        'FROM __source("raw_orders") AS o\n'
        'LEFT JOIN __ref("returns") AS r ON r.order_id = o.order_id\n'
    ),
    "models/returns.sql": (
        'MODEL (description "Returns");\n\n'
        'SELECT order_id, amount * -1 AS refund FROM __ref("orders")\n'
    ),
    "models/order_summary.sql": (
        'MODEL (description "Summary");\n\nSELECT * FROM __ref("returns")\n'
    ),
    "models/order_audit.sql": (
        'MODEL (description "Audit");\n\n'
        'SELECT order_id, missing_column FROM __ref("order_audit")\n'
    ),
}
_ORDERS_PROJECT: dict[str, str] = {
    "sqlbuild_project.toml": 'name = "orders_cycle"\nadapter = "duckdb"\n',
    "models/orders.sql": 'MODEL (description "Orders");\n\nSELECT order_id FROM __ref("returns")\n',
    "models/returns.sql": 'MODEL (description "Returns");\n\nSELECT order_id FROM __ref("orders")\n',
}


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedAnalysisTestCase(
            description="stars, CTEs, CTE facts, set operations, untyped inputs, contracts, pivots",
            seed=20261008,
            count=6,
            model_count=24,
            inference_profiles=_DIALECT_PROFILES,
            extra_files={},
            lineage_mode=ColumnLineageMode.FAST,
            expected_minimum_native=500,
            expected_minimum_expression_shapes=40,
            expected_minimum_pivot_proofs=80,
            expected_minimum_proven_pivots=12,
            expected_minimum_native_enrichments=90,
        ),
        GeneratedAnalysisTestCase(
            description="rich lineage over untyped inputs, CTE facts and contracts",
            seed=20261008,
            count=6,
            model_count=24,
            inference_profiles=_DIALECT_PROFILES,
            extra_files={},
            lineage_mode=ColumnLineageMode.RICH,
            expected_minimum_native=500,
            expected_minimum_expression_shapes=40,
            expected_minimum_pivot_proofs=80,
            expected_minimum_proven_pivots=12,
            expected_minimum_native_enrichments=90,
        ),
        GeneratedAnalysisTestCase(
            description="snowflake and duckdb adapter rules, fast lineage",
            seed=20261010,
            count=3,
            model_count=24,
            inference_profiles=_ADAPTER_PROFILES,
            extra_files=ADAPTER_RULE_MODELS,
            lineage_mode=ColumnLineageMode.FAST,
            expected_minimum_native=200,
            expected_minimum_expression_shapes=15,
            expected_minimum_pivot_proofs=30,
            expected_minimum_proven_pivots=10,
            expected_minimum_native_enrichments=30,
        ),
        GeneratedAnalysisTestCase(
            description="snowflake and duckdb adapter rules, rich lineage",
            seed=20261010,
            count=3,
            model_count=24,
            inference_profiles=_ADAPTER_PROFILES,
            extra_files=ADAPTER_RULE_MODELS,
            lineage_mode=ColumnLineageMode.RICH,
            expected_minimum_native=190,
            expected_minimum_expression_shapes=15,
            expected_minimum_pivot_proofs=30,
            expected_minimum_proven_pivots=10,
            expected_minimum_native_enrichments=20,
        ),
        GeneratedAnalysisTestCase(
            description="a project-local adapter's own nullability rules, called back natively",
            seed=20261011,
            count=3,
            model_count=24,
            inference_profiles=_CUSTOM_RULE_PROFILES,
            extra_files=ADAPTER_RULE_MODELS,
            lineage_mode=ColumnLineageMode.FAST,
            expected_minimum_native=1,
            expected_minimum_expression_shapes=1,
            expected_minimum_pivot_proofs=1,
            expected_minimum_proven_pivots=1,
            expected_minimum_native_enrichments=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_projects_when_analysing_natively_then_cached_and_proven_runs_agree(
    test_case: GeneratedAnalysisTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_dir: Path = tmp_path / "records"
    monkeypatch.setenv(ANALYSIS_RECORD_DIR_ENV_VAR, str(record_dir))
    rng: random.Random = random.Random(test_case.seed)
    runs: NativeAnalysisRuns = NativeAnalysisRuns()
    for index in range(test_case.count):
        inputs: CompileProjectInputs = compile_inputs(
            project_dir=tmp_path / f"project_{index}",
            files={
                **generated_analysis_files(rng=rng, model_count=test_case.model_count),
                **test_case.extra_files,
            },
        )
        for profile_index, profile in enumerate(test_case.inference_profiles):
            analyse_natively(
                inputs=inputs,
                inference_profile=profile,
                lineage_mode=test_case.lineage_mode,
                runs=runs,
                cache_root=tmp_path / f"cache_{index}_{profile_index}",
                monkeypatch=monkeypatch,
            )
    kinds: Counter[str] = deferral_kinds(record_dir)
    kinds.pop("analysis_session:adapter_nullability_callback", None)

    assert mismatches(inputs=runs.names, expected=runs.uncached, actual=runs.cached) == []
    assert kinds == Counter()
    assert runs.analysed_models >= test_case.expected_minimum_native
    assert runs.expression_shapes >= test_case.expected_minimum_expression_shapes
    assert runs.pivot_proofs >= test_case.expected_minimum_pivot_proofs
    assert runs.standalone_proofs >= test_case.expected_minimum_pivot_proofs
    assert runs.session_proofs >= test_case.expected_minimum_pivot_proofs
    assert runs.proven_pivots >= test_case.expected_minimum_proven_pivots
    assert runs.native_enrichments >= test_case.expected_minimum_native_enrichments
    assert runs.native_column_objects == runs.native_column_values > 0


@pytest.mark.parametrize(
    "test_case",
    [
        SharedAnalysisTestCase(
            description="equal regional queries, missing-column readers and a unique summary",
            regions=("east", "west", "north", "south"),
            inexact_regions=("east", "west", "north"),
            dialects=("duckdb", "snowflake"),
            expected_analysed=24,
            expected_shared=22,
            expected_reanalysed=6,
            expected_unshared=2,
            expected_column_values=12,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_equal_model_queries_when_analysing_natively_then_shares_and_cached_runs_agree(
    test_case: SharedAnalysisTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_dir: Path = tmp_path / "records"
    monkeypatch.setenv(ANALYSIS_RECORD_DIR_ENV_VAR, str(record_dir))
    inputs: CompileProjectInputs = compile_inputs(
        project_dir=tmp_path / "project",
        files=shared_analysis_files(
            regions=test_case.regions, inexact_regions=test_case.inexact_regions
        ),
    )
    sessions: list[Any] = started_sessions(monkeypatch=monkeypatch)
    runs: NativeAnalysisRuns = NativeAnalysisRuns()

    _ = [
        analyse_natively(
            inputs=inputs,
            inference_profile=ExpressionInferenceProfile(sql_analysis_dialect=dialect),
            lineage_mode=ColumnLineageMode.FAST,
            runs=runs,
            cache_root=tmp_path / f"cache_{dialect}",
            monkeypatch=monkeypatch,
        )
        for dialect in test_case.dialects
    ]

    uncached: list[Any] = sessions[2::3]
    shared: int = sum(session.sharing[0] for session in uncached)

    assert mismatches(inputs=runs.names, expected=runs.uncached, actual=runs.cached) == []
    assert (
        runs.analysed_models,
        shared,
        sum(session.sharing[1] for session in uncached),
        runs.analysed_models - shared,
        deferral_kinds(record_dir),
        runs.native_column_objects,
        runs.native_column_values,
    ) == (
        test_case.expected_analysed,
        test_case.expected_shared,
        test_case.expected_reanalysed,
        test_case.expected_unshared,
        Counter(),
        test_case.expected_column_values,
        test_case.expected_column_values,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        CyclicAnalysisTestCase(
            description="a ref cycle, a model reading itself and a star consumer of the cycle",
            files=_CYCLIC_PROJECT,
            dialects=("duckdb", "snowflake"),
            lineage_modes=(ColumnLineageMode.FAST, ColumnLineageMode.RICH),
            expected_analysed=16,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cyclic_models_when_analysing_natively_then_session_answers_and_cached_runs_agree(
    test_case: CyclicAnalysisTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_dir: Path = tmp_path / "records"
    monkeypatch.setenv(ANALYSIS_RECORD_DIR_ENV_VAR, str(record_dir))
    inputs: CompileProjectInputs = compile_inputs(
        project_dir=tmp_path / "project", files=test_case.files
    )
    sessions: list[Any] = started_sessions(monkeypatch=monkeypatch)
    runs: NativeAnalysisRuns = NativeAnalysisRuns()

    _ = [
        analyse_natively(
            inputs=inputs,
            inference_profile=ExpressionInferenceProfile(sql_analysis_dialect=dialect),
            lineage_mode=lineage_mode,
            runs=runs,
            cache_root=tmp_path / f"cache_{dialect}_{lineage_mode.value}",
            monkeypatch=monkeypatch,
        )
        for dialect, lineage_mode in product(test_case.dialects, test_case.lineage_modes)
    ]

    assert mismatches(inputs=runs.names, expected=runs.uncached, actual=runs.cached) == []
    assert (
        runs.analysed_models,
        len(sessions) // 3,
        None in sessions,
        deferral_kinds(record_dir),
    ) == (
        test_case.expected_analysed,
        len(test_case.dialects) * len(test_case.lineage_modes),
        False,
        Counter(),
    )


@pytest.mark.parametrize(
    "test_case",
    [
        CyclicCompileTestCase(
            description="a ref cycle, a model reading itself and a star consumer of the cycle",
            files=_CYCLIC_PROJECT,
            expected_exit_code=0,
            expected_compiled=(
                "models/order_audit.sql",
                "models/order_summary.sql",
                "models/orders.sql",
                "models/returns.sql",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cyclic_project_when_compiling_then_native_output_is_complete_and_repeatable(
    test_case: CyclicCompileTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_dir: Path = tmp_path / "records"
    monkeypatch.setenv(ANALYSIS_RECORD_DIR_ENV_VAR, str(record_dir))
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, CompilerEngine.NATIVE.value)
    native: tuple[int, object, object, dict[str, str]] = compiled_project_view(
        project_dir=tmp_path / "native" / "orders_cycle", files=test_case.files, capsys=capsys
    )
    native_deferrals: Counter[str] = deferral_kinds(record_dir)

    repeated: tuple[int, object, object, dict[str, str]] = compiled_project_view(
        project_dir=tmp_path / "repeated" / "orders_cycle", files=test_case.files, capsys=capsys
    )

    assert native == repeated
    assert (native[0], tuple(native[3]), native_deferrals) == (
        test_case.expected_exit_code,
        test_case.expected_compiled,
        Counter(),
    )


@pytest.mark.parametrize(
    "test_case",
    [
        InternalFailureTestCase(
            description="two analysed models sharing a name break the session's invariant",
            files=_ORDERS_PROJECT,
            expected_message=(
                "NativeCompilerError: native model analysis: two analysed models share a name"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_internal_native_failure_when_assembling_then_raises_without_python_analysis(
    test_case: InternalFailureTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_dir: Path = tmp_path / "records"
    monkeypatch.setenv(ANALYSIS_RECORD_DIR_ENV_VAR, str(record_dir))
    inputs: CompileProjectInputs = compile_inputs(
        project_dir=tmp_path / "project", files=test_case.files
    )
    python_analyses: list[object] = record_python_model_analyses(monkeypatch=monkeypatch)
    duplicate_analysed_model_names(monkeypatch=monkeypatch)

    with pytest.raises(native_module.NativeCompilerError) as raised:
        _ = assemble_compiled_project(
            inputs=inputs,
            inference_profile=ExpressionInferenceProfile(sql_analysis_dialect="duckdb"),
        )

    assert (str(raised.value), python_analyses, deferral_kinds(record_dir)) == (
        test_case.expected_message,
        [],
        Counter(),
    )


@pytest.mark.parametrize(
    "test_case",
    [
        StandalonePivotProofTestCase(
            description="a selection that leaves the pivots out of model analysis",
            analysed_models=frozenset({"orders_list"}),
            expected_native_proofs=2,
            expected_session_proofs=2,
            expected_proven_by_model={
                "orders_list": None,
                "status_amounts": True,
                "status_passthrough": True,
            },
        ),
        StandalonePivotProofTestCase(
            description="no model analysis, so the proofs run without a session",
            analysed_models=frozenset(),
            expected_native_proofs=2,
            expected_session_proofs=0,
            expected_proven_by_model={
                "orders_list": None,
                "status_amounts": True,
                "status_passthrough": True,
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unanalysed_pivot_model_when_assembling_then_native_proves_it_without_the_wheel(
    test_case: StandalonePivotProofTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs: CompileProjectInputs = compile_inputs(
        project_dir=tmp_path / "project", files=pivot_project_files()
    )
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, CompilerEngine.NATIVE_PREVIEW.value)
    recorded: NativePivotProofs = native_pivot_proofs(monkeypatch=monkeypatch)

    project: CompiledProject = assemble_compiled_project(
        inputs=inputs,
        inference_profile=ExpressionInferenceProfile(sql_analysis_dialect="duckdb"),
        analysis_model_names=test_case.analysed_models,
    )

    assert (
        all(proof is not None for proof in recorded.proofs),
        len(recorded.proofs),
        recorded.session_proofs,
        {
            model.name: getattr(model.dynamic_column_contract, "output_proven", None)
            for model in project.models
        },
    ) == (
        True,
        test_case.expected_native_proofs,
        test_case.expected_session_proofs,
        test_case.expected_proven_by_model,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        AdapterRuleCallbackTestCase(
            description="the adapter's own rule answers natively analysed CTE nullability",
            seed=20261012,
            model_count=6,
            raised=None,
            expected_minimum_calls=1,
        ),
        AdapterRuleCallbackTestCase(
            description="the adapter rule's exception reaches the caller unchanged",
            seed=20261012,
            model_count=6,
            raised=LookupError,
            expected_minimum_calls=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_nullability_rule_when_analysing_natively_then_rule_is_called_back(
    test_case: AdapterRuleCallbackTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[InferredNullability, ...]] = []
    raised: list[type[Exception]] = []

    def adapter_rule(arguments: tuple[InferredNullability, ...]) -> InferredNullability:
        calls.append(arguments)
        if raised:
            raise raised[0]("adapter rule failed")
        return InferredNullability.NULLABLE

    request: NativeModelAnalysisRequest = analysis_request(
        inputs=compile_inputs(
            project_dir=tmp_path / "project",
            files={
                **generated_analysis_files(
                    rng=random.Random(test_case.seed), model_count=test_case.model_count
                ),
                **ADAPTER_RULE_MODELS,
            },
        ),
        monkeypatch=monkeypatch,
        inference_profile=ExpressionInferenceProfile(
            sql_analysis_dialect="duckdb",
            function_nullability_rules={"UPPER": adapter_rule, "IFF": adapter_rule},
        ),
    )
    calls.clear()
    raised.extend(filter(None, (test_case.raised,)))
    record_dir: Path = tmp_path / "records"
    monkeypatch.setenv(ANALYSIS_RECORD_DIR_ENV_VAR, str(record_dir))

    if test_case.raised is None:
        assert analyze_native_model_sql(request=request).analyses
    else:
        with pytest.raises(test_case.raised, match="adapter rule failed"):
            _ = analyze_native_model_sql(request=request)

    assert len(calls) >= test_case.expected_minimum_calls, test_case.description
    assert all(isinstance(value, InferredNullability) for args in calls for value in args)
    assert deferral_kinds(record_dir) == Counter(
        {"analysis_session:adapter_nullability_callback": 1}
    ), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
