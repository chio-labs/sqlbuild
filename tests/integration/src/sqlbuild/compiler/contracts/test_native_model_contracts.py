"""Native contract validation and promotion conflicts equal Python's on generated projects."""

from __future__ import annotations

import random
from collections import Counter
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.sql_analysis.constants import ANALYSIS_RECORD_DIR_ENV_VAR
from tests.integration.src.sqlbuild.compiler.contracts._test_types import (
    DeferredContractTestCase,
    GeneratedContractParityTestCase,
    GeneratedPromotionParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.contracts.helpers import (
    NativeContractRecord,
    compiled_contract_project,
    contract_views,
    deferral_records,
    perturbed_project,
    promotion_settings,
    promotion_views,
    record_native_outcomes,
    record_native_promotion_calls,
    with_declared_type,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedContractParityTestCase(
            description="enforced, implicit, typed, nullability and dynamic contracts",
            seed=20261009,
            variants=60,
            dialects=(None, "duckdb", "postgres", "snowflake", "bigquery", "databricks", "tsql"),
            expected_minimum_native=800,
            expected_minimum_typed_comparisons=300,
            expected_minimum_diagnostics=2000,
            expected_codes=frozenset({"K001", "K002", "K003", "K004", "K005", "K006", "K011"}),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_contracts_when_validating_natively_then_diagnostics_match_python(
    test_case: GeneratedContractParityTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    record: NativeContractRecord = record_native_outcomes(monkeypatch=monkeypatch)
    base: CompiledProject = compiled_contract_project(project_dir=tmp_path / "project")
    labels: list[object] = []
    python_views: list[object] = []
    native_views: list[object] = []
    for variant in range(test_case.variants):
        project: CompiledProject = perturbed_project(project=base, rng=rng)
        for dialect in test_case.dialects:
            python, native = contract_views(
                project=project, dialect=dialect, monkeypatch=monkeypatch
            )
            labels.append((variant, dialect))
            python_views.append(python)
            native_views.append(native)

    assert mismatches(inputs=labels, expected=python_views, actual=native_views) == []
    assert record.statuses["native"] >= test_case.expected_minimum_native
    assert record.statuses["typed_comparisons"] >= test_case.expected_minimum_typed_comparisons
    assert record.statuses["native_diagnostics"] >= test_case.expected_minimum_diagnostics
    assert set(record.codes) >= test_case.expected_codes


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedPromotionParityTestCase(
            description="lifecycle configs under explicit and adapter-default promotion modes",
            seed=20261010,
            variants=400,
            expected_minimum_conflicts=30,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_lifecycles_when_finding_promotion_conflicts_natively_then_match_python(
    test_case: GeneratedPromotionParityTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    calls: Counter[str] = record_native_promotion_calls(monkeypatch=monkeypatch)
    base: CompiledProject = compiled_contract_project(project_dir=tmp_path / "project")
    labels: list[object] = []
    python_views: list[object] = []
    native_views: list[object] = []
    for variant in range(test_case.variants):
        project: CompiledProject = perturbed_project(project=base, rng=rng)
        adapter_default, settings_file = promotion_settings(rng=rng)
        python, native = promotion_views(
            project=project,
            adapter_default=adapter_default,
            settings_file=settings_file,
            monkeypatch=monkeypatch,
        )
        labels.append(variant)
        python_views.append(python)
        native_views.append(native)

    assert mismatches(inputs=labels, expected=python_views, actual=native_views) == []
    assert calls["calls"] == test_case.variants
    assert calls["conflicts"] >= test_case.expected_minimum_conflicts


@pytest.mark.parametrize(
    "test_case",
    [
        DeferredContractTestCase(
            description="a declared type outside ASCII",
            declared_type="TÉXT",
            dialect="duckdb",
            expected_kind="type_normalization",
            expected_deferred_models=1,
        ),
        DeferredContractTestCase(
            description="a dialect outside the native type system",
            declared_type="INTEGER",
            dialect="mysql",
            expected_kind="type_normalization",
            expected_deferred_models=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_input_native_cannot_answer_when_validating_then_python_answers_and_it_is_recorded(
    test_case: DeferredContractTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_dir: Path = tmp_path / "records"
    record: NativeContractRecord = record_native_outcomes(monkeypatch=monkeypatch)
    project: CompiledProject = with_declared_type(
        project=compiled_contract_project(project_dir=tmp_path / "project"),
        declared_type=test_case.declared_type,
    )
    monkeypatch.setenv(ANALYSIS_RECORD_DIR_ENV_VAR, str(record_dir))

    python, native = contract_views(
        project=project, dialect=test_case.dialect, monkeypatch=monkeypatch
    )

    assert native == python
    assert record.statuses[test_case.expected_kind] == test_case.expected_deferred_models
    assert (
        deferral_records(record_dir)
        == [{"kind": test_case.expected_kind, "site": "contracts/columns.py"}]
        * test_case.expected_deferred_models
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
