from __future__ import annotations

from pathlib import Path

import pytest

from scripts.dupscore.main.build_pair_evidence import build_pair_evidence
from scripts.dupscore.main.build_report import build_report
from scripts.dupscore.main.build_report_delta import build_report_delta
from scripts.dupscore.models import (
    DupscoreConfig,
    DupscoreReport,
    PairEvidenceReport,
    ReportDelta,
)
from tests.unit.scripts.dupscore.main.build_report._test_types import (
    BuildReportTestCase,
    ReportDeltaTestCase,
)
from tests.unit.scripts.dupscore.main.build_report.helpers import (
    BASE_PROJECT_FILES,
    TWIN_PROJECT_FILES,
    commit_all,
    initialize_repo,
    write_project_files,
)

_CONFIG: DupscoreConfig = DupscoreConfig(persisted_state_surfaces=("sqlbuild.alpha.state",))


@pytest.mark.parametrize(
    "test_case",
    [
        BuildReportTestCase(
            description="ranks the planner and executor seam first with multi-signal evidence",
            expected_top_pair=("sqlbuild.alpha.executor", "sqlbuild.alpha.planner"),
            expected_signal_names=("callgraph_shape", "same_name_symbols", "state_fanin"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seeded_repo_when_building_report_then_ranks_seam_first(
    test_case: BuildReportTestCase,
    tmp_path: Path,
) -> None:
    repo_root: Path = tmp_path / "repo"
    repo_root.mkdir()
    initialize_repo(repo_root)
    write_project_files(repo_root=repo_root, files=BASE_PROJECT_FILES | TWIN_PROJECT_FILES)
    _ = commit_all(repo_root=repo_root, message="seed project")

    report: DupscoreReport = build_report(repo_root=repo_root, revision=None, config=_CONFIG)

    assert report.entries
    assert report.entries[0].package_pair == test_case.expected_top_pair
    top_signals: tuple[str, ...] = tuple(
        contribution.signal_name for contribution in report.entries[0].contributions
    )
    for expected_signal in test_case.expected_signal_names:
        assert expected_signal in top_signals

    evidence: PairEvidenceReport = build_pair_evidence(
        report=report,
        left=test_case.expected_top_pair[1],
        right=test_case.expected_top_pair[0],
    )
    assert evidence.combined_rank == 1
    assert evidence.contributions


@pytest.mark.parametrize(
    "test_case",
    [
        ReportDeltaTestCase(
            description="reports a newly introduced twin against a base revision",
            expected_new_twin_fragment="resolve_target_relation",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_new_twin_when_comparing_revisions_then_reports_new_same_name_evidence(
    test_case: ReportDeltaTestCase,
    tmp_path: Path,
) -> None:
    repo_root: Path = tmp_path / "repo"
    repo_root.mkdir()
    initialize_repo(repo_root)
    write_project_files(repo_root=repo_root, files=BASE_PROJECT_FILES)
    base_revision: str = commit_all(repo_root=repo_root, message="seed project without twin")
    write_project_files(repo_root=repo_root, files=TWIN_PROJECT_FILES)
    _ = commit_all(repo_root=repo_root, message="introduce twin")

    base_report: DupscoreReport = build_report(
        repo_root=repo_root, revision=base_revision, config=_CONFIG
    )
    current_report: DupscoreReport = build_report(
        repo_root=repo_root, revision=None, config=_CONFIG
    )
    delta: ReportDelta = build_report_delta(base=base_report, current=current_report, top=10)

    assert any(
        test_case.expected_new_twin_fragment in evidence
        for evidence in delta.new_same_name_evidence
    )
