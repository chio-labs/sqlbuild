"""A differing project keeps both engines' target, stderr and compiled-test stats."""

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
    fake_run_engine,
    first_stat_paths,
    kept_files,
)


@pytest.mark.parametrize(
    "test_case",
    [
        FailureEvidenceTestCase(
            description="differing warm stderr keeps both engines' evidence",
            stderr_by_engine={
                "python": "Semantic checks were partial for 1 models:\n",
                "native-preview": "SQL test planning  START\n",
            },
            expected_files=(
                "example__orders/native-preview/0-compile-warm.stderr",
                "example__orders/native-preview/compiled-tests-stat.tsv",
                "example__orders/native-preview/target/compiled/tests/orders/test_orders.sql",
                "example__orders/native-preview/target/sql-test-artifacts.json",
                "example__orders/python/0-compile-warm.stderr",
                "example__orders/python/compiled-tests-stat.tsv",
                "example__orders/python/target/compiled/tests/orders/test_orders.sql",
                "example__orders/python/target/sql-test-artifacts.json",
            ),
            expected_evidence_engines=("native-preview", "python"),
        ),
        FailureEvidenceTestCase(
            description="identical runs keep nothing",
            stderr_by_engine={"python": "done\n", "native-preview": "done\n"},
            expected_files=(),
            expected_evidence_engines=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_engine_runs_when_comparing_then_only_differing_projects_keep_evidence(
    test_case: FailureEvidenceTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        project_comparison,
        "run_engine",
        fake_run_engine(stderr_by_engine=test_case.stderr_by_engine),
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
            engines=("python", "native-preview"),
            work_dir=tmp_path / "work",
            jobs=1,
            stage_captures=False,
            python=Path("python"),
            engine_environment={},
            evidence_dir=evidence_dir,
        ),
    )
    stats: list[str] = first_stat_paths(
        evidence_dir=evidence_dir, engines=test_case.expected_evidence_engines
    )

    assert (bool(comparison.differences), kept_files(evidence_dir), stats) == (
        bool(test_case.expected_files),
        test_case.expected_files,
        ["orders/test_orders.sql"] * len(test_case.expected_evidence_engines),
    )
