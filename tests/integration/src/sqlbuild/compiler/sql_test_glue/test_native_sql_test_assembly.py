"""SQL tests assembled natively equal Python's assembly, which answers native deferrals."""

from __future__ import annotations

import random
from collections import Counter
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.compiler.helpers import mismatches
from tests.integration.src.sqlbuild.compiler.sql_test_glue._test_types import (
    GeneratedSqlTestAssemblyParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.sql_test_glue.helpers import (
    INVERTED_WINDOW,
    NO_WINDOW,
    VALID_WINDOW,
    PlanningCallOutcome,
    SqlTestCorpusShape,
    assembly_outcome,
    generated_sql_test_assembly_files,
    outcome_kind,
    python_assembly_outcome,
    record_native_assemblies,
    write_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedSqlTestAssemblyParityTestCase(
            description="model, direct, parameterized and mock-reads-helper tests",
            seed=20261010,
            count=4,
            test_count=12,
            shape=SqlTestCorpusShape(
                windows=(NO_WINDOW, VALID_WINDOW, INVERTED_WINDOW),
                stray_window_share=0.1,
                helper_redefinition_share=0.15,
                assertion_share=0.2,
                unflattenable_assertion_share=0.1,
            ),
            expected_native_assemblies={
                "native_assembled": 181,
                "native_with_diagnostics": 17,
                "native_case_fingerprints": 96,
                "deferred_macro_mocks": 4,
                "deferred_non_ascii_text": 11,
                "deferred_decimal_context": 5,
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_sql_tests_when_assembling_natively_then_compiled_tests_match_python(
    test_case: GeneratedSqlTestAssemblyParityTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    native_assemblies: Counter[str] = record_native_assemblies(monkeypatch=monkeypatch)
    differences: list[tuple[object, object, object]] = []
    outcomes: Counter[str] = Counter()
    for index in range(test_case.count):
        project_dir: Path = tmp_path / f"project_{index}"
        write_project(
            project_dir=project_dir,
            files=generated_sql_test_assembly_files(
                rng=rng, test_count=test_case.test_count, shape=test_case.shape
            ),
        )
        expected: PlanningCallOutcome = python_assembly_outcome(
            project_dir=project_dir, monkeypatch=monkeypatch
        )
        actual: PlanningCallOutcome = assembly_outcome(project_dir=project_dir)
        differences.extend(mismatches(inputs=[index], expected=[expected], actual=[actual]))
        outcomes[outcome_kind(actual)] += 1

    assert (differences, dict(native_assemblies)) == (
        [],
        test_case.expected_native_assemblies,
    ), outcomes
