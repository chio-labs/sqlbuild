"""Every engine locates reference scan errors identically and reports them as CompileInputError."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.compiler_differential.constants import FAILURE_BASE_FILES, FAILURE_MART_PATH
from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    ReferenceScanErrorTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    CompileReuseRun,
    lifecycle_error_type,
    report_without_engine,
    run_reuse_compile,
    stderr_without_durations,
    write_project_file,
)

_ENGINES: tuple[str, str, str] = ("python", "native", "native-preview")
_MART_HEADER: str = 'MODEL (\n  description "Order totals per customer",\n);\n\n'


@pytest.mark.parametrize(
    "test_case",
    [
        ReferenceScanErrorTestCase(
            description="unclosed_reference_call",
            mart_body='SELECT customer_id, 1 AS total_amount\nFROM __ref("stg_orders"\n',
            expected_message=(
                f"{FAILURE_MART_PATH}:6:6: SQL reference contains an unclosed parenthesis"
            ),
            expected_error_types=("CompileInputError",) * 3,
        ),
        ReferenceScanErrorTestCase(
            description="unclosed_quote_after_a_rejected_call",
            mart_body=(
                "SELECT customer_id, 1 AS total_amount\nFROM __ref(stg_orders)\n"
                "WHERE 'é' <> 'open\n"
            ),
            expected_message=(
                f"{FAILURE_MART_PATH}:7:14: SQL reference contains an unclosed quoted string"
            ),
            expected_error_types=("CompileInputError",) * 3,
        ),
        ReferenceScanErrorTestCase(
            description="empty_table_function_argument",
            mart_body=(
                "SELECT customer_id, 1 AS total_amount\n"
                'FROM __ref("stg_orders") JOIN __table_fn("orders_for")(1, , 2) USING (customer_id)\n'
            ),
            expected_message=(
                f"{FAILURE_MART_PATH}:6:31: SQL reference contains an empty argument"
            ),
            expected_error_types=("CompileInputError",) * 3,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_reference_scan_error_when_compiling_with_each_engine_then_located_and_typed_alike(
    test_case: ReferenceScanErrorTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir: Path = tmp_path / "orders"
    runs: list[CompileReuseRun] = []
    error_types: list[str] = []
    for engine in _ENGINES:
        shutil.rmtree(project_dir, ignore_errors=True)
        for relative_path, contents in {
            **FAILURE_BASE_FILES,
            FAILURE_MART_PATH: _MART_HEADER + test_case.mart_body,
        }.items():
            write_project_file(project_dir, relative_path, contents)
        runs.append(
            run_reuse_compile(project_dir=project_dir, global_args=("--compiler-engine", engine))
        )
        error_types.append(
            lifecycle_error_type(project_dir=project_dir, engine=engine, monkeypatch=monkeypatch)
        )

    assert (
        tuple(run.returncode for run in runs),
        {report_without_engine(run) for run in runs} == {report_without_engine(runs[0])},
        {stderr_without_durations(stderr=run.stderr) for run in runs}
        == {stderr_without_durations(stderr=runs[0].stderr)},
        test_case.expected_message in runs[0].report,
        tuple(error_types),
    ) == ((1, 1, 1), True, True, True, test_case.expected_error_types), (
        runs[0].report,
        runs[2].report,
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
