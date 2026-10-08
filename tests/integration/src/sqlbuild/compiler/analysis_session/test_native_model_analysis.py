"""The native model analysis session equals Python's model analysis on generated projects."""

from __future__ import annotations

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
from sqlbuild.compiler.compile.models import CompileProjectInputs
from sqlbuild.compiler.sql_analysis.constants import ANALYSIS_RECORD_DIR_ENV_VAR
from tests.integration.src.sqlbuild.compiler.analysis_session._test_types import (
    AnalysisFallbackTestCase,
    GeneratedAnalysisParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.analysis_session.helpers import (
    AnalysisParity,
    analysis_request,
    compare_analyses,
    compile_inputs,
    deferral_kinds,
    generated_analysis_files,
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
            description="stars, CTEs, set operations, untyped inputs, contracts and a pivot",
            seed=20261008,
            count=6,
            model_count=24,
            dialects=("duckdb", "postgres", "snowflake", "bigquery"),
            expected_minimum_native=500,
            expected_minimum_expression_shapes=40,
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
    assert (
        parity.analysed_models - kinds["analysis_session:legacy_analysis"]
        >= test_case.expected_minimum_native
    )
    assert parity.expression_shapes >= test_case.expected_minimum_expression_shapes


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


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
