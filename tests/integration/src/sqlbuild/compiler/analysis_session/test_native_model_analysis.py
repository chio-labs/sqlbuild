"""The native model analysis session equals Python's model analysis on generated projects."""

from __future__ import annotations

import pickle
import random
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
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
from sqlbuild.compiler.sql_analysis.constants import ANALYSIS_RECORD_DIR_ENV_VAR
from sqlbuild.rule_engine._helpers.engine.custom_rules import host_project
from sqlbuild.rule_engine._helpers.host.custom_host_pool import host_payload_project
from tests.integration.src.sqlbuild.compiler.analysis_session._test_types import (
    AnalysisFallbackTestCase,
    GeneratedAnalysisParityTestCase,
    HostPayloadTestCase,
    SessionFailureTestCase,
    StandalonePivotProofTestCase,
)
from tests.integration.src.sqlbuild.compiler.analysis_session.helpers import (
    AnalysisParity,
    FailingProvideSession,
    NativePivotProofs,
    analysis_request,
    compare_analyses,
    compile_inputs,
    deferral_kinds,
    failing_provide_sessions,
    generated_analysis_files,
    native_pivot_proofs,
    pivot_project_files,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches

_ORDERS_PROJECT: dict[str, str] = {
    "sqlbuild_project.toml": 'name = "orders_cycle"\nadapter = "duckdb"\n',
    "models/orders.sql": 'MODEL (description "Orders");\n\nSELECT order_id FROM __ref("returns")\n',
    "models/returns.sql": 'MODEL (description "Returns");\n\nSELECT order_id FROM __ref("orders")\n',
}


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedAnalysisParityTestCase(
            description="stars, CTEs, set operations, untyped inputs, contracts, contract CTEs, pivots",
            seed=20261008,
            count=6,
            model_count=24,
            dialects=("duckdb", "postgres", "snowflake", "bigquery"),
            expected_minimum_native=500,
            expected_minimum_expression_shapes=40,
            expected_minimum_pivot_proofs=80,
            expected_minimum_proven_pivots=12,
            expected_maximum_enrichment_deferrals=120,
            expected_minimum_native_enrichments=90,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_projects_when_analysing_natively_then_matches_python(
    test_case: GeneratedAnalysisParityTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_dir: Path = tmp_path / "records"
    monkeypatch.setenv(ANALYSIS_RECORD_DIR_ENV_VAR, str(record_dir))
    rng: random.Random = random.Random(test_case.seed)
    parity: AnalysisParity = AnalysisParity()
    for index in range(test_case.count):
        inputs: CompileProjectInputs = compile_inputs(
            project_dir=tmp_path / f"project_{index}",
            files=generated_analysis_files(rng=rng, model_count=test_case.model_count),
        )
        for dialect in test_case.dialects:
            compare_analyses(inputs=inputs, dialect=dialect, parity=parity, monkeypatch=monkeypatch)
    kinds: Counter[str] = deferral_kinds(record_dir)

    assert mismatches(inputs=parity.names, expected=parity.python, actual=parity.native) == []
    assert kinds["analysis_session:session"] == kinds["analysis_session:expression_shapes"] == 0
    assert kinds["analysis_session:dynamic_pivot"] == 0
    assert (
        parity.analysed_models - kinds["analysis_session:legacy_analysis"]
        >= test_case.expected_minimum_native
    )
    assert parity.expression_shapes >= test_case.expected_minimum_expression_shapes
    assert parity.pivot_proofs >= test_case.expected_minimum_pivot_proofs
    assert parity.standalone_proofs >= test_case.expected_minimum_pivot_proofs
    assert parity.session_proofs >= test_case.expected_minimum_pivot_proofs
    assert parity.proven_pivots >= test_case.expected_minimum_proven_pivots
    assert (
        kinds["analysis_session:input_enrichment"]
        <= test_case.expected_maximum_enrichment_deferrals
    )
    assert parity.native_enrichments >= test_case.expected_minimum_native_enrichments


@pytest.mark.parametrize(
    "test_case",
    [
        AnalysisFallbackTestCase(
            description="models that reference each other",
            files=_ORDERS_PROJECT,
            allow_compact_analysis=True,
            keeps_catalog=True,
            expected_kind="session",
        ),
        AnalysisFallbackTestCase(
            description="lineage disabled, so compact analysis is off",
            files=_ORDERS_PROJECT,
            allow_compact_analysis=False,
            keeps_catalog=True,
            expected_kind="no_compact_analysis",
        ),
        AnalysisFallbackTestCase(
            description="an inference profile without a binding catalog",
            files=_ORDERS_PROJECT,
            allow_compact_analysis=True,
            keeps_catalog=False,
            expected_kind="no_analysis_catalog",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_analysis_when_analysing_natively_then_python_analyses_and_records(
    test_case: AnalysisFallbackTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_dir: Path = tmp_path / "records"
    request: NativeModelAnalysisRequest = analysis_request(
        inputs=compile_inputs(project_dir=tmp_path / "project", files=test_case.files),
        monkeypatch=monkeypatch,
    )
    profile: ExpressionInferenceProfile = request.inference_profile
    monkeypatch.setenv(ANALYSIS_RECORD_DIR_ENV_VAR, str(record_dir))

    analyses: object = analyze_native_model_sql(
        request=replace(
            request,
            allow_compact_analysis=test_case.allow_compact_analysis,
            inference_profile=replace(
                profile, binding_catalog=(None, profile.binding_catalog)[test_case.keeps_catalog]
            ),
        )
    )

    assert analyses is None
    assert deferral_kinds(record_dir) == Counter({f"analysis_session:{test_case.expected_kind}": 1})


@pytest.mark.parametrize(
    "test_case",
    [
        SessionFailureTestCase(
            description="untyped inputs defer enrichments before the session fails",
            seed=20261009,
            model_count=12,
            expected_kinds={"analysis_session:session": 1},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_session_failure_after_deferrals_when_analysing_then_records_only_the_session(
    test_case: SessionFailureTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_dir: Path = tmp_path / "records"
    request: NativeModelAnalysisRequest = analysis_request(
        inputs=compile_inputs(
            project_dir=tmp_path / "project",
            files=generated_analysis_files(
                rng=random.Random(test_case.seed), model_count=test_case.model_count
            ),
        ),
        monkeypatch=monkeypatch,
    )
    sessions: list[FailingProvideSession] = failing_provide_sessions(monkeypatch=monkeypatch)
    monkeypatch.setenv(ANALYSIS_RECORD_DIR_ENV_VAR, str(record_dir))

    analyses: object = analyze_native_model_sql(request=request)

    assert analyses is None
    assert sum(session.answered for session in sessions) > 0
    assert deferral_kinds(record_dir) == Counter(test_case.expected_kinds)


@pytest.mark.parametrize(
    "test_case",
    [
        StandalonePivotProofTestCase(
            description="a selection that leaves the pivots out of model analysis",
            analysed_models=frozenset({"orders_list"}),
            expected_native_proofs=2,
            expected_session_answers=[True, True],
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
            expected_session_answers=[False, False],
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
        recorded.session_answers,
        {
            model.name: getattr(model.dynamic_column_contract, "output_proven", None)
            for model in project.models
        },
    ) == (
        True,
        test_case.expected_native_proofs,
        test_case.expected_session_answers,
        test_case.expected_proven_by_model,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        HostPayloadTestCase(
            description="a pivot project analysed in one native session",
            expected_models=("orders_list", "status_amounts", "status_passthrough"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_native_session_when_publishing_rule_host_payload_then_session_is_dropped(
    test_case: HostPayloadTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs: CompileProjectInputs = compile_inputs(
        project_dir=tmp_path / "project", files=pivot_project_files()
    )
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, CompilerEngine.NATIVE_PREVIEW.value)
    project: CompiledProject = assemble_compiled_project(
        inputs=inputs, inference_profile=ExpressionInferenceProfile(sql_analysis_dialect="duckdb")
    )

    payload: CompiledProject = pickle.loads(
        pickle.dumps(host_payload_project(host_project(project)))
    )

    assert project.native_session is not None
    assert (payload.native_session, tuple(sorted(model.name for model in payload.models))) == (
        None,
        test_case.expected_models,
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
