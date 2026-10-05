"""Project input fingerprint edge cases for whole-project compile reuse."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

import pytest

from sqlbuild.cli.compile_reuse._helpers.project_files import (
    carried_forward_digests,
    compare_project_files,
    restamped_paths,
    snapshot_project_files,
)
from sqlbuild.cli.compile_reuse.models import ProjectFilesComparison, StoredProjectFile
from sqlbuild.cli.compile_reuse.types import FileStamp
from tests.unit.src.sqlbuild.cli.compile_reuse._helpers._test_types import (
    DigestCarryForwardTestCase,
    LinkCycleTestCase,
    ProjectFingerprintTestCase,
    RacyRewriteTestCase,
    RestampTestCase,
)
from tests.unit.src.sqlbuild.cli.compile_reuse._helpers.helpers import (
    add_file_in_linked_directory,
    break_link,
    edit_link_target,
    later_snapshot_ns,
    retarget_link,
    rewrite_same_size_keeping_mtime,
    stat_only_project_files,
    stored_project_files,
    touch_without_change,
    write_file,
    write_fingerprint_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ProjectFingerprintTestCase(
            description="no_change", change=lambda _root: None, expected_unchanged=True
        ),
        ProjectFingerprintTestCase(
            description="mtime_only_change_same_content",
            change=touch_without_change,
            expected_unchanged=True,
        ),
        ProjectFingerprintTestCase(
            description="same_size_and_mtime_new_content",
            change=rewrite_same_size_keeping_mtime,
            expected_unchanged=False,
        ),
        ProjectFingerprintTestCase(
            description="file_added",
            change=lambda root: write_file(root / "models/returns.sql", "SELECT 1\n"),
            expected_unchanged=False,
        ),
        ProjectFingerprintTestCase(
            description="file_removed",
            change=lambda root: (root / "macros/currency.py").unlink(),
            expected_unchanged=False,
        ),
        ProjectFingerprintTestCase(
            description="empty_directory_added",
            change=lambda root: (root / "models/_sqlbuild").mkdir(),
            expected_unchanged=False,
        ),
        ProjectFingerprintTestCase(
            description="nested_hidden_directory_edit",
            change=lambda root: write_file(root / "models/.drafts/returns.sql", "SELECT 22\n"),
            expected_unchanged=False,
        ),
        ProjectFingerprintTestCase(
            description="file_link_target_edit", change=edit_link_target, expected_unchanged=False
        ),
        ProjectFingerprintTestCase(
            description="file_link_retarget", change=retarget_link, expected_unchanged=False
        ),
        ProjectFingerprintTestCase(
            description="file_added_in_linked_directory",
            change=add_file_in_linked_directory,
            expected_unchanged=False,
        ),
        ProjectFingerprintTestCase(
            description="file_link_broken", change=break_link, expected_unchanged=False
        ),
        ProjectFingerprintTestCase(
            description="database_file_removed",
            change=lambda root: (root / "warehouse.duckdb").unlink(),
            expected_unchanged=False,
        ),
        ProjectFingerprintTestCase(
            description="database_file_content_change",
            change=lambda root: write_file(root / "warehouse.duckdb", "rewritten database pages"),
            expected_unchanged=True,
        ),
        ProjectFingerprintTestCase(
            description="target_directory_change",
            change=lambda root: write_file(
                root / "target/compiled/models/orders.sql", "SELECT 2\n"
            ),
            expected_unchanged=True,
        ),
        ProjectFingerprintTestCase(
            description="compute_log_change",
            change=lambda root: write_file(root / "logs/compile-2.log", "next compile log\n"),
            expected_unchanged=True,
        ),
        ProjectFingerprintTestCase(
            description="bytecode_cache_change",
            change=lambda root: write_file(root / "macros/__pycache__/currency.pyc", "bytecode 2"),
            expected_unchanged=True,
        ),
        ProjectFingerprintTestCase(
            description="root_hidden_directory_change",
            change=lambda root: write_file(root / ".venv/lib/vendored.py", "VALUE = 2\n"),
            expected_unchanged=True,
        ),
        ProjectFingerprintTestCase(
            description="root_editor_settings_change",
            change=lambda root: write_file(root / ".vscode/settings.json", '{"tabs": 2}\n'),
            expected_unchanged=True,
        ),
        ProjectFingerprintTestCase(
            description="root_hidden_project_directory_change",
            change=lambda root: write_file(root / ".orders_rules/limits.txt", "10\n"),
            expected_unchanged=False,
        ),
        ProjectFingerprintTestCase(
            description="version_control_metadata_change",
            change=lambda root: write_file(root / ".git/HEAD", "ref: refs/heads/feature\n"),
            expected_unchanged=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_stored_fingerprint_when_project_changes_then_change_is_detected_exactly(
    test_case: ProjectFingerprintTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_fingerprint_project(tmp_path)
    stored: dict[str, StoredProjectFile] = stored_project_files(
        project_dir=project_dir, snapshot_ns=later_snapshot_ns()
    )

    test_case.change(project_dir)
    comparison: ProjectFilesComparison = compare_project_files(
        project_dir=str(project_dir),
        stored=stored,
        current=snapshot_project_files(project_dir=str(project_dir)),
    )

    assert comparison.unchanged is test_case.expected_unchanged


@pytest.mark.parametrize(
    "test_case",
    [
        DigestCarryForwardTestCase(
            description="touched_model",
            change=touch_without_change,
            expected_verified=frozenset({"models/orders.sql"}),
            expected_carried=frozenset({"models/orders.sql", "macros/currency.py"}),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_touched_file_with_same_content_when_checking_then_its_digest_carries_forward(
    test_case: DigestCarryForwardTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_fingerprint_project(tmp_path)
    stored: dict[str, StoredProjectFile] = stored_project_files(
        project_dir=project_dir, snapshot_ns=later_snapshot_ns()
    )
    test_case.change(project_dir)
    current: dict[str, FileStamp] = snapshot_project_files(project_dir=str(project_dir))

    comparison: ProjectFilesComparison = compare_project_files(
        project_dir=str(project_dir), stored=stored, current=current
    )
    digests: dict[str, str] = carried_forward_digests(
        stored=stored, current=current, verified=comparison.verified
    )

    assert comparison.unchanged
    assert frozenset(comparison.verified) == test_case.expected_verified
    assert test_case.expected_carried <= frozenset(digests)
    assert {path: digests[path] for path in test_case.expected_carried} == {
        path: stored[path].digest for path in test_case.expected_carried
    }


@pytest.mark.parametrize(
    "test_case",
    [
        RestampTestCase(
            description="touched_file_without_digest",
            change=touch_without_change,
            expected_unchanged=False,
            expected_restamped=frozenset({"models/orders.sql"}),
        ),
        RestampTestCase(
            description="unchanged_file_without_digest",
            change=lambda _root: None,
            expected_unchanged=True,
            expected_restamped=frozenset(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_stat_only_stored_files_when_a_stamp_moves_then_it_misses_and_is_queued_for_hashing(
    test_case: RestampTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_fingerprint_project(tmp_path)
    stored: dict[str, StoredProjectFile] = stat_only_project_files(project_dir=project_dir)

    test_case.change(project_dir)
    current: dict[str, FileStamp] = snapshot_project_files(project_dir=str(project_dir))
    comparison: ProjectFilesComparison = compare_project_files(
        project_dir=str(project_dir), stored=stored, current=current
    )

    assert comparison.unchanged is test_case.expected_unchanged
    assert comparison.verified == {}
    assert restamped_paths(stored=stored, current=current) == test_case.expected_restamped


@pytest.mark.parametrize(
    "test_case",
    [
        RacyRewriteTestCase(description="racy_stamp_rehashed", racy=True, expected_unchanged=False),
        RacyRewriteTestCase(
            description="settled_stamp_trusted", racy=False, expected_unchanged=True
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_rewrite_within_one_timestamp_tick_when_checking_then_only_racy_stamps_rehash(
    test_case: RacyRewriteTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_fingerprint_project(tmp_path)
    stored: dict[str, StoredProjectFile] = stored_project_files(
        project_dir=project_dir, snapshot_ns=time.time_ns()
    )
    current: dict[str, FileStamp] = snapshot_project_files(project_dir=str(project_dir))
    (project_dir / "models/orders.sql").write_text("SELECT 9 AS order_id\n", encoding="utf-8")
    stored["models/orders.sql"] = replace(
        stored["models/orders.sql"], stamp=current["models/orders.sql"], racy=test_case.racy
    )

    comparison: ProjectFilesComparison = compare_project_files(
        project_dir=str(project_dir), stored=stored, current=current
    )

    assert comparison.unchanged is test_case.expected_unchanged


@pytest.mark.parametrize(
    "test_case",
    [
        LinkCycleTestCase(
            description="link_to_project_root",
            link_path="models/loop",
            expected_present=("models/loop", "models/orders.sql"),
            expected_descended_prefix="models/loop/",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_directory_link_cycle_when_snapshotting_then_walk_terminates(
    test_case: LinkCycleTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_fingerprint_project(tmp_path)
    (project_dir / test_case.link_path).symlink_to(project_dir, target_is_directory=True)

    snapshot: dict[str, FileStamp] = snapshot_project_files(project_dir=str(project_dir))

    assert frozenset(test_case.expected_present) <= frozenset(snapshot)
    assert not any(path.startswith(test_case.expected_descended_prefix) for path in snapshot)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
