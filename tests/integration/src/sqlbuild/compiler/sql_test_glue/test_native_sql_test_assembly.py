"""SQL tests assembled natively match the tests, diagnostics and errors recorded from Python's
assembly, which the native assembly replaces.

Expected outputs were recorded once from the pre-port Python assembly (`_assemble_compiled_sql_test`)
into `tests/goldens/python_oracle/sql_test_assembly_*.json`.
"""

from __future__ import annotations

import random
from collections import Counter
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.compiler.golden_views import (
    GoldenEntry,
    golden_differences,
    golden_name,
    read_golden,
)
from tests.integration.src.sqlbuild.compiler.sql_test_glue._test_types import (
    EdgeSqlTestAssemblyTestCase,
    GeneratedSqlTestAssemblyParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.sql_test_glue.helpers import (
    EDGE_DECIMAL_CONTEXT,
    EDGE_DECIMAL_OVERFLOW,
    EDGE_DEEP_HELPER,
    EDGE_INVALID_UNREAD_HELPER,
    EDGE_UNICODE_CONTENTS,
    EDGE_UNICODE_MACRO_SCOPE,
    INVERTED_WINDOW,
    NO_WINDOW,
    VALID_WINDOW,
    PlanningCallOutcome,
    SqlTestCorpusShape,
    assembly_golden_entry,
    assembly_outcome,
    edge_sql_test_files,
    generated_sql_test_assembly_files,
    outcome_kind,
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
                "native_assembled": 201,
                "native_with_diagnostics": 26,
                "native_case_fingerprints": 101,
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
    entries: list[GoldenEntry] = []
    outcomes: Counter[str] = Counter()
    for index in range(test_case.count):
        project_dir: Path = tmp_path / f"project_{index}"
        write_project(
            project_dir=project_dir,
            files=generated_sql_test_assembly_files(
                rng=rng, test_count=test_case.test_count, shape=test_case.shape
            ),
        )
        actual: PlanningCallOutcome = assembly_outcome(project_dir=project_dir)
        entries.append(assembly_golden_entry(outcome=actual, project_dir=project_dir))
        outcomes[outcome_kind(actual)] += 1

    assert (
        golden_differences(
            read_golden(golden_name("sql_test_assembly", test_case.description)), entries
        ),
        dict(native_assemblies),
    ) == ([], test_case.expected_native_assemblies), outcomes


@pytest.mark.parametrize(
    "test_case",
    [
        EdgeSqlTestAssemblyTestCase(
            description="non-ASCII test contents, case-folded reads and located diagnostics",
            files={"tests/unit/test_unicode.sql": EDGE_UNICODE_CONTENTS},
            expected_outcome="answered",
        ),
        EdgeSqlTestAssemblyTestCase(
            description="a mock reading a deeply nested helper whose nested CTE shadows another",
            files={"tests/unit/test_deep.sql": EDGE_DEEP_HELPER},
            expected_outcome="answered",
        ),
        EdgeSqlTestAssemblyTestCase(
            description="decimal case parameters the default context rounds and flushes",
            files={"tests/unit/test_decimal.sql": EDGE_DECIMAL_CONTEXT},
            expected_outcome="answered",
        ),
        EdgeSqlTestAssemblyTestCase(
            description="a decimal case parameter the default context overflows",
            files={"tests/unit/test_decimal.sql": EDGE_DECIMAL_OVERFLOW},
            expected_outcome="raised",
        ),
        EdgeSqlTestAssemblyTestCase(
            description="a macro test over a model with a non-ASCII name after @",
            files=EDGE_UNICODE_MACRO_SCOPE,
            expected_outcome="answered",
        ),
        EdgeSqlTestAssemblyTestCase(
            description="an unread helper with an invalid reference call",
            files={"tests/unit/test_invalid.sql": EDGE_INVALID_UNREAD_HELPER},
            expected_outcome="answered",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_edge_sql_test_when_assembling_natively_then_matches_recorded_python(
    test_case: EdgeSqlTestAssemblyTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / golden_name("edge", test_case.description)
    write_project(project_dir=project_dir, files=edge_sql_test_files(extra_files=test_case.files))

    actual: PlanningCallOutcome = assembly_outcome(project_dir=project_dir)

    assert (
        golden_differences(
            read_golden(golden_name("sql_test_assembly", test_case.description)),
            [assembly_golden_entry(outcome=actual, project_dir=project_dir)],
        ),
        outcome_kind(actual),
    ) == ([], test_case.expected_outcome)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
