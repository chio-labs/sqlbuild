"""A failing project keeps its target, stderr and compiled-test stats."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.compiler_differential._helpers.comparing import project_comparison
from scripts.compiler_differential.models import (
    CorpusProject,
    DifferentialCommand,
    DifferentialOptions,
    ExpectedOutcome,
    ProjectComparison,
)
from tests.unit.scripts.compiler_differential._helpers.running._test_types import (
    FailureEvidenceTestCase,
)
from tests.unit.scripts.compiler_differential._helpers.running.helpers import (
    fake_run_project,
    first_stat_paths,
    kept_files,
)


@pytest.mark.parametrize(
    "test_case",
    [
        FailureEvidenceTestCase(
            description="failing warm compile keeps evidence",
            exit_code=1,
            expected_files=(
                "example__orders/0-compile-warm.stderr",
                "example__orders/compiled-tests-stat.tsv",
                "example__orders/target/compiled/tests/orders/test_orders.sql",
                "example__orders/target/sql-test-artifacts.json",
            ),
        ),
        FailureEvidenceTestCase(
            description="passing runs keep nothing",
            exit_code=0,
            expected_files=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_runs_when_checking_then_only_failing_projects_keep_evidence(
    test_case: FailureEvidenceTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        project_comparison,
        "run_project",
        fake_run_project(exit_code=test_case.exit_code),
    )
    evidence_dir: Path = tmp_path / "evidence"

    comparison: ProjectComparison = project_comparison.compare_project(
        project=CorpusProject(
            name="example/orders",
            commands=(DifferentialCommand(label="compile-warm", arguments=("compile",)),),
            expected=ExpectedOutcome(),
            source_dir=tmp_path,
        ),
        options=DifferentialOptions(
            work_dir=tmp_path / "work",
            jobs=1,
            stage_captures=False,
            python=Path("python"),
            evidence_dir=evidence_dir,
        ),
    )
    stats: list[str] = first_stat_paths(evidence_dir=evidence_dir)

    assert (bool(comparison.differences), kept_files(evidence_dir), stats) == (
        bool(test_case.expected_files),
        test_case.expected_files,
        ["orders/test_orders.sql"] * bool(test_case.expected_files),
    )
