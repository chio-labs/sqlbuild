"""Real-CLI coverage of one partial mock read by two real models of a SQL test chain."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.test._test_types import (
    SharedPartialFixtureE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.test.helpers import (
    build_shared_partial_fixture_project_files,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        SharedPartialFixtureE2ETestCase(
            description="both readers spell the column the same way",
            enriched_column="discount",
            report_column="discount",
            expected_padding_count=1,
        ),
        SharedPartialFixtureE2ETestCase(
            description="readers spell the column in different case",
            enriched_column="DISCOUNT",
            report_column="discount",
            expected_padding_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_partial_mock_read_by_two_real_models_when_testing_then_pads_each_column_once(
    test_case: SharedPartialFixtureE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="shared_partial_fixture",
        repo_files=build_shared_partial_fixture_project_files(
            enriched_column=test_case.enriched_column, report_column=test_case.report_column
        ),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "test"), project_dir=project_dir
    )

    assert result.returncode == 0, result.stdout + result.stderr
    statements: str = "".join(
        path.read_text(encoding="utf-8")
        for path in (project_dir / "target" / "run" / "tests").rglob("*.sql")
    )
    assert (
        statements.lower().count('cast(null as double) as "discount"')
        == test_case.expected_padding_count
    ), statements


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
