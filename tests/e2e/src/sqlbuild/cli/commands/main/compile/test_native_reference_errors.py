"""Every engine locates reference scan errors identically and reports them as CompileInputError."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.compiler_differential.constants import (
    FAILURE_BASE_CONFIG,
    FAILURE_BASE_FILES,
    FAILURE_MART_PATH,
)
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
_CALL_LOG: str = "macro_calls.log"
_EMIT_MACRO: str = (
    "from pathlib import Path\n\n\n"
    "def emit(expression: str) -> str:\n"
    '    """Return the expression, logging each execution."""\n\n'
    f"    with (Path(__file__).resolve().parents[1] / {_CALL_LOG!r}).open(\n"
    '        "a", encoding="utf-8"\n'
    "    ) as log:\n"
    '        _ = log.write("call\\n")\n'
    "    return expression\n"
)
_MART_HEADER: str = 'MODEL (\n  description "Order totals per customer",\n);\n\n'
_QUOTED_NOTE: str = "over 12\\\" boxes, by customer's orders"
_NO_SQL_ANALYSIS_CONFIG: str = FAILURE_BASE_CONFIG + "\n[settings]\nsql_analysis = false\n"


@pytest.mark.parametrize(
    "test_case",
    [
        ReferenceScanErrorTestCase(
            description="unclosed_reference_call",
            project_files={
                FAILURE_MART_PATH: _MART_HEADER
                + 'SELECT customer_id, 1 AS total_amount\nFROM __ref("stg_orders"\n'
            },
            expected_message=(
                f"{FAILURE_MART_PATH}:6:6: SQL reference contains an unclosed parenthesis"
            ),
            expected_macro_calls=(0, 0, 0),
            expected_error_types=("CompileInputError",) * 3,
        ),
        ReferenceScanErrorTestCase(
            description="unclosed_quote_after_a_rejected_call",
            project_files={
                FAILURE_MART_PATH: _MART_HEADER
                + "SELECT customer_id, 1 AS total_amount\nFROM __ref(stg_orders)\n"
                "WHERE 'é' <> 'open\n"
            },
            expected_message=(
                f"{FAILURE_MART_PATH}:7:14: SQL reference contains an unclosed quoted string"
            ),
            expected_macro_calls=(0, 0, 0),
            expected_error_types=("CompileInputError",) * 3,
        ),
        ReferenceScanErrorTestCase(
            description="empty_table_function_argument",
            project_files={
                FAILURE_MART_PATH: _MART_HEADER + "SELECT customer_id, 1 AS total_amount\n"
                'FROM __ref("stg_orders") JOIN __table_fn("orders_for")(1, , 2) USING (customer_id)\n'
            },
            expected_message=(
                f"{FAILURE_MART_PATH}:6:31: SQL reference contains an empty argument"
            ),
            expected_macro_calls=(0, 0, 0),
            expected_error_types=("CompileInputError",) * 3,
        ),
        ReferenceScanErrorTestCase(
            description="header_string_with_an_escaped_quote_and_apostrophe",
            project_files={
                FAILURE_MART_PATH: f'MODEL (\n  description "{_QUOTED_NOTE}",\n);\n\n'
                'SELECT customer_id, 1 AS total_amount\nFROM __ref("stg_orders")\nWHERE "open = 1\n'
            },
            expected_message=(
                f"{FAILURE_MART_PATH}:7:7: SQL reference contains an unclosed quoted string"
            ),
            expected_macro_calls=(0, 0, 0),
            expected_error_types=("CompileInputError",) * 3,
        ),
        ReferenceScanErrorTestCase(
            description="macro_output_fault_before_an_authored_fault_is_unlocated",
            project_files={
                "macros/emit.py": _EMIT_MACRO,
                FAILURE_MART_PATH: _MART_HEADER
                + "SELECT customer_id, @emit('__ref(1') AS total_amount\n"
                'FROM __ref("stg_orders"\n',
            },
            expected_message=(
                f"{FAILURE_MART_PATH}: SQL reference contains an unclosed parenthesis"
            ),
            expected_macro_calls=(1, 2, 2),
            expected_error_types=("CompileInputError",) * 3,
        ),
        ReferenceScanErrorTestCase(
            description="authored_fault_after_a_macro_is_located_without_a_python_rerun",
            project_files={
                "macros/emit.py": _EMIT_MACRO,
                FAILURE_MART_PATH: _MART_HEADER + "SELECT customer_id, @emit('1') AS total_amount\n"
                'FROM __ref("stg_orders"\n',
            },
            expected_message=(
                f"{FAILURE_MART_PATH}:6:6: SQL reference contains an unclosed parenthesis"
            ),
            expected_macro_calls=(1, 1, 1),
            expected_error_types=("CompileInputError",) * 3,
        ),
        ReferenceScanErrorTestCase(
            description="test_file_header_names_the_file",
            project_files={
                "tests/unit/test_customer_totals.sql": (
                    'TEST (\n  name "totals_by_note",\n  parameters (note string),\n'
                    f'  cases (boxes (note "{_QUOTED_NOTE}")),\n);\n\nWITH\n'
                    "__ref__stg_orders AS (\n"
                    "  SELECT 10 AS customer_id, CAST(5 AS DOUBLE) AS amount\n),\n"
                    "__expected__customer_totals AS (\n"
                    '  SELECT 10 AS customer_id, 5 AS total_amount, @param("note") AS note\n),\n'
                    "__assert__totals AS (\n"
                    '  SELECT * FROM __table_fn("orders_for")(1, , 2)\n)\n'
                )
            },
            expected_message=(
                "tests/unit/test_customer_totals.sql: SQL reference contains an empty argument"
            ),
            expected_macro_calls=(0, 0, 0),
            expected_error_types=("CompileInputError",) * 3,
        ),
        ReferenceScanErrorTestCase(
            description="audit_file_header_names_the_file",
            project_files={
                "audits/generic/positive_total.sql": (
                    "AUDIT (\n  -- totals over 12\" boxes, by customer's orders\n"
                    "  severity warn\n);\n\n"
                    'SELECT * FROM __ref("@model") WHERE note = \'open\n'
                ),
                FAILURE_MART_PATH: FAILURE_BASE_FILES[FAILURE_MART_PATH].replace(
                    "  description", "  audits [positive_total],\n  description"
                ),
            },
            expected_message=(
                "audits/generic/positive_total.sql: SQL reference contains an unclosed quoted string"
            ),
            expected_macro_calls=(0, 0, 0),
            expected_error_types=("CompileInputError",) * 3,
        ),
        ReferenceScanErrorTestCase(
            description="function_file_header_names_the_file",
            project_files={
                "sqlbuild_project.toml": _NO_SQL_ANALYSIS_CONFIG,
                "functions/sql/orders_for.sql": (
                    f'FUNCTION (\n  description "{_QUOTED_NOTE}",\n'
                    "  arguments (p_customer_id INTEGER),\n  returns INTEGER\n);\n\n"
                    'SELECT COUNT(*) FROM __ref("stg_orders" WHERE customer_id = p_customer_id\n'
                ),
            },
            expected_message=(
                "functions/sql/orders_for.sql: SQL reference contains an unclosed parenthesis"
            ),
            expected_macro_calls=(0, 0, 0),
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
    macro_calls: list[int] = []
    error_types: list[str] = []
    for engine in _ENGINES:
        shutil.rmtree(project_dir, ignore_errors=True)
        for relative_path, contents in {
            **FAILURE_BASE_FILES,
            _CALL_LOG: "",
            **test_case.project_files,
        }.items():
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
        {report_without_engine(run) for run in runs} == {report_without_engine(runs[0])},
        {stderr_without_durations(stderr=run.stderr) for run in runs}
        == {stderr_without_durations(stderr=runs[0].stderr)},
        test_case.expected_message in runs[0].report,
        tuple(macro_calls),
        tuple(error_types),
    ) == (
        (1, 1, 1),
        True,
        True,
        True,
        test_case.expected_macro_calls,
        test_case.expected_error_types,
    ), (runs[0].report, runs[2].report)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
