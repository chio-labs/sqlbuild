"""Every engine reports SQL test, scenario and relationship errors identically."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.compiler_differential._helpers.corpus.attachment_failure_cases import (
    attachment_failure_cases,
)
from scripts.compiler_differential._helpers.corpus.scope_failure_cases import scope_failure_cases
from scripts.compiler_differential.constants import FAILURE_BASE_MART, FAILURE_MART_PATH
from scripts.compiler_differential.models import FailureCase
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    CompileReuseRun,
    lifecycle_error_type,
    report_without_engine,
    run_reuse_compile,
    stderr_without_durations,
    write_project_file,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.sql_test_errors._test_types import (
    NativeSqlTestErrorTestCase,
)

_ENGINES: tuple[str, ...] = ("python", "native", "native-preview")
_CALL_LOG: str = "macro_calls.log"
_COUNTED_MACRO: str = (
    "from pathlib import Path\n\n\n"
    "def counted(expression: str) -> str:\n"
    '    """Return the expression, logging each execution."""\n\n'
    f"    with (Path(__file__).resolve().parents[1] / {_CALL_LOG!r}).open(\n"
    '        "a", encoding="utf-8"\n'
    "    ) as log:\n"
    '        _ = log.write("call\\n")\n'
    "    return expression\n"
)
_CASES: dict[str, FailureCase] = {
    case.name: case for case in (*attachment_failure_cases(), *scope_failure_cases())
}


@pytest.mark.parametrize(
    "test_case",
    [
        NativeSqlTestErrorTestCase(
            description="a scenario fixture without a target name",
            case_name="scenario-fixture-without-target",
            expected_distinct_macro_call_counts=1,
        ),
        NativeSqlTestErrorTestCase(
            description="a scenario macro mock",
            case_name="scenario-macro-mock",
            expected_distinct_macro_call_counts=1,
        ),
        NativeSqlTestErrorTestCase(
            description="a scenario without checks",
            case_name="scenario-without-checks",
            expected_distinct_macro_call_counts=1,
        ),
        NativeSqlTestErrorTestCase(
            description="a scenario statement after its CTEs",
            case_name="scenario-statement-after-ctes",
            expected_distinct_macro_call_counts=1,
        ),
        NativeSqlTestErrorTestCase(
            description="a scenario check reading a project source",
            case_name="scenario-check-reads-source",
            expected_distinct_macro_call_counts=1,
        ),
        NativeSqlTestErrorTestCase(
            description="dependent scenario checks, still checked by Python's Polyglot parse",
            case_name="scenario-dependent-checks",
            expected_distinct_macro_call_counts=1,
        ),
        NativeSqlTestErrorTestCase(
            description="the first of two broken scenarios",
            case_name="scenario-first-of-two-errors",
            expected_distinct_macro_call_counts=1,
        ),
        NativeSqlTestErrorTestCase(
            description="a quoted scenario CTE name",
            case_name="scenario-quoted-cte-name",
            expected_distinct_macro_call_counts=1,
            expected_location="--> tests/scenarios/orders.sql:6:1",
        ),
        NativeSqlTestErrorTestCase(
            description="a materialized scenario CTE",
            case_name="scenario-materialized-cte",
            expected_distinct_macro_call_counts=1,
            expected_location="--> tests/scenarios/orders.sql:6:25",
        ),
        NativeSqlTestErrorTestCase(
            description="a quoted macro test CTE name",
            case_name="macro-test-quoted-cte-name",
            expected_distinct_macro_call_counts=1,
            expected_location="--> tests/unit/test_stg_orders.sql:4:1",
        ),
        NativeSqlTestErrorTestCase(
            description="a test mocking an unknown source",
            case_name="test-mocks-unknown-source",
            expected_distinct_macro_call_counts=1,
        ),
        NativeSqlTestErrorTestCase(
            description="a scoped scenario's expected CTE without a target",
            case_name="scope-scenario-expected-without-target",
            expected_distinct_macro_call_counts=1,
        ),
        NativeSqlTestErrorTestCase(
            description="a scoped macro test whose actual CTE has no body",
            case_name="scope-macro-test-cte-without-body",
            expected_distinct_macro_call_counts=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_test_error_when_compiling_with_each_engine_then_errors_and_types_match(
    test_case: NativeSqlTestErrorTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case: FailureCase = _CASES[test_case.case_name]
    runs: list[CompileReuseRun] = []
    macro_calls: list[int] = []
    error_types: list[str] = []
    project_dir: Path = tmp_path / "orders"
    files: dict[str, str] = {
        **case.files,
        "macros/counted.py": _COUNTED_MACRO,
        FAILURE_MART_PATH: FAILURE_BASE_MART.replace("SUM(amount)", "SUM(@counted('amount'))"),
        _CALL_LOG: "",
    }
    for engine in _ENGINES:
        shutil.rmtree(project_dir, ignore_errors=True)
        for relative_path, contents in files.items():
            write_project_file(project_dir, relative_path, contents)
        runs.append(
            run_reuse_compile(project_dir=project_dir, global_args=("--compiler-engine", engine))
        )
        macro_calls.append(len((project_dir / _CALL_LOG).read_text(encoding="utf-8").splitlines()))
        error_types.append(
            lifecycle_error_type(project_dir=project_dir, engine=engine, monkeypatch=monkeypatch)
        )

    assert (
        tuple(run.returncode for run in runs),
        {report_without_engine(run) for run in runs[1:]} == {report_without_engine(runs[0])},
        {stderr_without_durations(stderr=run.stderr) for run in runs[1:]}
        == {stderr_without_durations(stderr=runs[0].stderr)},
        f"[{case.expected_code}]" in runs[0].report + runs[0].stderr,
        str(case.expected_message) in runs[0].report + runs[0].stderr,
        (case.expected_help or "") in runs[0].report + runs[0].stderr,
        test_case.expected_location in runs[0].report + runs[0].stderr,
        len(set(macro_calls)),
        tuple(error_types),
    ) == (
        (1, 1, 1),
        True,
        True,
        True,
        True,
        True,
        True,
        test_case.expected_distinct_macro_call_counts,
        ("CompileInputError", "CompileInputError", "CompileInputError"),
    ), (
        runs[0].report,
        runs[0].stderr,
        runs[2].report,
        macro_calls,
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
