"""The harness finds a project with table functions and hidden references identical by engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.compiler_differential.constants import FAILURE_BASE_FILES
from scripts.compiler_differential.main.differential import run_compiler_differential
from tests.e2e.scripts.compiler_differential._test_types import HarnessRunTestCase
from tests.e2e.scripts.compiler_differential.helpers import harness_arguments

_REFERENCE_FILES: dict[str, str] = {
    **FAILURE_BASE_FILES,
    "functions/sql/orders_for.sql": (
        "FUNCTION (\n"
        '  description "Orders for one customer above a floor",\n'
        "  arguments (p_customer INTEGER, p_floor DOUBLE),\n"
        "  returns table (\n    order_id INTEGER,\n    amount DOUBLE\n  ),\n);\n\n"
        'SELECT order_id, amount\nFROM __ref("stg_orders")\n'
        "WHERE customer_id = p_customer AND amount >= p_floor\n"
    ),
    "models/marts/customer_totals.sql": (
        'MODEL (\n  description "Order totals per customer",\n);\n\n'
        '-- __ref("hidden_in_comment")\n'
        "SELECT o.customer_id, SUM(f.amount) AS total_amount,\n"
        '  \'__ref("hidden_in_string")\' AS note, $$__table_fn("hidden")(1)$$ AS raw_note\n'
        'FROM __ref("stg_orders") o\n'
        'CROSS JOIN __table_fn("orders_for")\n  (10, /* floor, */ 1.5) f\n'
        "GROUP BY o.customer_id\n"
    ),
}


@pytest.mark.parametrize(
    "test_case",
    [
        HarnessRunTestCase(
            description="table_functions_and_hidden_references",
            extra_arguments=(),
            expected_exit_code=0,
            expected_lines=(
                "OK   project/table_function_orders",
                "Compiler differential passed: 1 projects identical (python vs native-preview)",
            ),
            expected_patterns=(),
            expected_absent=("DIFF",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_table_function_project_when_comparing_engines_then_harness_passes(
    test_case: HarnessRunTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project_dir: Path = tmp_path / "table_function_orders"
    for relative_path, contents in _REFERENCE_FILES.items():
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8", newline="\n")

    exit_code: int = run_compiler_differential(
        harness_arguments(
            work_dir=tmp_path / "work", extra=test_case.extra_arguments, project=project_dir
        )
    )

    output: str = capsys.readouterr().out
    assert exit_code == test_case.expected_exit_code, output
    assert all(line in output for line in test_case.expected_lines), output
    assert not any(text in output for text in test_case.expected_absent), output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
