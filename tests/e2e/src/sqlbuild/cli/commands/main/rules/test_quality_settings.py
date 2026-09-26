"""Project settings remain enforced across real CLI processes and warm caches."""

import subprocess
import sys
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.rules._test_types import (
    OverrideSettingsCase,
    RankingSettingsCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RankingSettingsCase("lowered cap invalidates cached success", 1, 1, "SQBRSQL043"),
        RankingSettingsCase("zero is not an off switch", 0, 1, "positive integer"),
    ],
    ids=lambda case: case.description,
)
def test_given_cached_ranking_success_when_project_limit_changes_then_enforces_new_limit(
    test_case: RankingSettingsCase, tmp_path: Path
) -> None:
    project: Path = tmp_path / "sqlbuild_project.toml"
    config: str = 'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = ["SQBRSQL043"]\n'
    project.write_text(config + "max_ranking_order_by = 2\n")
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        "MODEL (); WITH items AS (SELECT 1 AS a, 2 AS b) "
        "SELECT ROW_NUMBER() OVER (ORDER BY a, b) AS row_id FROM items"
    )
    command: list[str] = [
        str(Path(sys.executable).with_name("sqb")),
        "--project-dir",
        str(tmp_path),
        "compile",
        "--json",
    ]
    initial: subprocess.CompletedProcess[str] = subprocess.run(
        command, capture_output=True, text=True, timeout=30, check=False
    )
    assert initial.returncode == 0, initial.stdout + initial.stderr
    project.write_text(config + f"max_ranking_order_by = {test_case.next_limit}\n")
    changed: subprocess.CompletedProcess[str] = subprocess.run(
        command, capture_output=True, text=True, timeout=30, check=False
    )
    assert changed.returncode == test_case.expected_exit
    assert test_case.expected_message in changed.stdout + changed.stderr


@pytest.mark.parametrize(
    "test_case",
    [OverrideSettingsCase("closed policy rejects cached suppression")],
    ids=lambda case: case.description,
)
def test_given_cached_suppression_when_overrides_are_forbidden_then_compile_fails(
    test_case: OverrideSettingsCase, tmp_path: Path
) -> None:
    project: Path = tmp_path / "sqlbuild_project.toml"
    config: str = 'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = ["SQBRSQL001"]\n'
    project.write_text(config)
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        "MODEL ();\n-- sqb: ignore SQBRSQL001 because example\nSELECT 1 AS order_id WHERE 1 = NULL"
    )
    command: list[str] = [
        str(Path(sys.executable).with_name("sqb")),
        "--project-dir",
        str(tmp_path),
        "compile",
        "--json",
    ]
    initial: subprocess.CompletedProcess[str] = subprocess.run(
        command, capture_output=True, text=True, timeout=30, check=False
    )
    assert initial.returncode == 0, initial.stdout + initial.stderr
    project.write_text(config + "allow_model_overrides = false\n")
    changed: subprocess.CompletedProcess[str] = subprocess.run(
        command, capture_output=True, text=True, timeout=30, check=False
    )
    assert changed.returncode == test_case.expected_exit
    assert test_case.expected_message in changed.stdout + changed.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-vv"]))
