"""Integration coverage for native lint repair through the real CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    FixCommandIntegrationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        FixCommandIntegrationTestCase(
            description="multiple native repairs converge through project expansion",
            selected_rules=(
                "SQBL001",
                "SQBL003",
                "SQBL005",
                "SQBL006",
                "SQBL012",
                "SQBL016",
                "SQBL017",
                "SQBL025",
                "SQBL030",
            ),
            original_sql=(
                'MODEL (description "Native fix integration");\n'
                "WITH unused AS (SELECT 9 AS id), source AS (\n"
                "  SELECT id, value, CASE WHEN active THEN TRUE ELSE FALSE END AS active\n"
                "  FROM items\n"
                ")\n"
                "SELECT DISTINCT\n"
                "  value AS value,\n"
                "  COUNT(1) AS row_count\n"
                "FROM source\n"
                "JOIN other ON source.id = other.id\n"
                "WHERE value = NULL\n"
                "GROUP BY value\n"
            ),
            expected_sql=(
                'MODEL (description "Native fix integration");\n'
                "WITH source AS (\n"
                "  SELECT id, value, COALESCE(active, FALSE) AS active\n"
                "  FROM items\n"
                ")\n"
                "SELECT value,\n"
                "  COUNT(*) AS row_count\n"
                "FROM source\n"
                "INNER JOIN other ON source.id = other.id\n"
                "WHERE value IS NULL\n"
                "GROUP BY value\n"
            ),
            expected_fixed_codes=(
                "SQBL001",
                "SQBL005",
                "SQBL006",
                "SQBL016",
                "SQBL017",
                "SQBL025",
                "SQBL030",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_fixable_project_when_running_fix_twice_then_real_cli_converges(
    test_case: FixCommandIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    selected: str = ", ".join(f'"{code}"' for code in test_case.selected_rules)
    _ = (tmp_path / "sqlbuild_project.toml").write_text(
        f'name = "demo"\nadapter = "duckdb"\n[lint]\nselect = [{selected}]\n',
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "fixed.sql"
    model.parent.mkdir()
    _ = model.write_text(test_case.original_sql, encoding="utf-8")

    first_exit: int = main(["--no-color", "--project-dir", str(tmp_path), "fix"])
    first_output: str = capsys.readouterr().out
    second_exit: int = main(["--no-color", "--project-dir", str(tmp_path), "fix", "--check"])
    second_output: str = capsys.readouterr().out

    assert first_exit == 0
    assert second_exit == 0
    assert model.read_text(encoding="utf-8") == test_case.expected_sql
    for code in test_case.expected_fixed_codes:
        assert f"fixed[{code}]" in first_output
    assert "REMAINING=0" in first_output
    assert "WOULD_FIX=0" in second_output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
