"""The harness finds a scoped project with relationship grants identical under both engines."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.compiler_differential.constants import FAILURE_BASE_FILES
from scripts.compiler_differential.main.differential import run_compiler_differential
from tests.e2e.scripts.compiler_differential._test_types import HarnessRunTestCase
from tests.e2e.scripts.compiler_differential.helpers import harness_arguments

_SCOPED_FILES: dict[str, str] = {
    **FAILURE_BASE_FILES,
    "macros/amounts.py": "def doubled(value):\n    return f'{value} * 2'\n",
    "models/staging/_enums/status.sql": "ENUM (name staged_status, members [PLACED]);\n",
    "models/marts/_constants/limits.sql": "CONSTANT (name minimum_total, value 1);\n",
    "models/staging/stg_orders.sql": (
        'MODEL (\n  description "Staged orders",\n);\n\n'
        "SELECT order_id, customer_id, @doubled('amount') AS amount, status\n"
        'FROM __source("raw_orders")\nWHERE status = @enum("staged_status").PLACED\n'
    ),
    "models/marts/customer_totals.sql": (
        'MODEL (\n  description "Order totals per customer",\n);\n\n'
        "SELECT customer_id, SUM(@doubled('amount')) AS total_amount\n"
        'FROM __ref("stg_orders")\nGROUP BY customer_id\n'
        'HAVING SUM(amount) >= @const("minimum_total")\n'
    ),
    "tests/unit/test_stg_orders.sql": (
        'TEST (name "staged_orders");\n\nWITH\n'
        "__source__raw_orders AS (\n"
        "  SELECT 1 AS order_id, 10 AS customer_id, CAST(5 AS DOUBLE) AS amount,"
        " 'PLACED' AS status\n),\n"
        "__expected__stg_orders AS (\n"
        "  SELECT 1 AS order_id, @doubled('5') AS amount,"
        ' @enum("staged_status").PLACED AS status\n)\nSELECT 1\n'
    ),
    "tests/unit/test_doubled.sql": (
        'TEST (mode macro, name "doubles_amounts");\n\nWITH\n'
        "__macro_actual__ AS (\n  SELECT @doubled('2') AS value\n),\n"
        "__macro_expected__ AS (\n  SELECT 4 AS value\n)\nSELECT 1\n"
    ),
}


@pytest.mark.parametrize(
    "test_case",
    [
        HarnessRunTestCase(
            description="scoped_declarations_with_relationship_grants",
            extra_arguments=(),
            expected_exit_code=0,
            expected_lines=(
                "OK   project/scoped_orders",
                "Compiler differential passed: 1 projects identical (python vs native-preview)",
            ),
            expected_patterns=(),
            expected_absent=("DIFF",),
        ),
        HarnessRunTestCase(
            description="shipped_native_stages_only",
            extra_arguments=("--engines", "python", "native"),
            expected_exit_code=0,
            expected_lines=(
                "OK   project/scoped_orders",
                "Compiler differential passed: 1 projects identical (python vs native)",
            ),
            expected_patterns=(),
            expected_absent=("DIFF",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_scoped_project_when_comparing_engines_then_harness_passes(
    test_case: HarnessRunTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project_dir: Path = tmp_path / "scoped_orders"
    for relative_path, contents in _SCOPED_FILES.items():
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
