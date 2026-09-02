"""Core execution history import boundary test."""

import subprocess
import sys

import pytest

from tests.unit.src.sqlbuild.runtime.execution_history._test_types import ImportCase


@pytest.mark.parametrize(
    "test_case",
    [
        ImportCase(
            description="public package loads without backend or orchestration dependencies",
            expected_forbidden_imports=(
                "sqlite3",
                "psycopg",
                "dagster",
                "kafka",
                "clickhouse_connect",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_clean_interpreter_when_importing_execution_history_then_optional_backends_are_not_loaded(
    test_case: ImportCase,
) -> None:
    module_names: str = ",".join(repr(name) for name in test_case.expected_forbidden_imports)
    script = (
        "import sys; import sqlbuild.execution_history; "
        f"forbidden=({module_names},); "
        "loaded=tuple(name for name in forbidden if name in sys.modules); print(repr(loaded))"
    )

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, "-c", script], check=True, capture_output=True, text=True
    )

    assert result.stdout.strip() == "()"
