"""Tests for the shared single-walk discovery snapshot."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.classes.directory_snapshot import DirectorySnapshot
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_helpers import (
    header_match_mismatches,
    isolated_discovery_mismatches,
    model_paths,
    snapshot_glob_mismatches,
    write_random_tree,
    write_scoped_project,
)
from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_types import (
    DiscoveryPassRefreshTestCase,
    NativeHeaderMatchTestCase,
    SharedSnapshotDiscoveryTestCase,
    SnapshotGlobTestCase,
    SnapshotScopeReuseTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotGlobTestCase("small_tree", seed=1, entry_count=40),
        SnapshotGlobTestCase("medium_tree", seed=2, entry_count=120),
        SnapshotGlobTestCase("large_tree", seed=3, entry_count=300),
    ],
    ids=lambda case: case.description,
)
def test_given_randomized_tree_when_globbing_snapshot_then_matches_pathlib_rglob(
    tmp_path: Path, test_case: SnapshotGlobTestCase
) -> None:
    write_random_tree(root=tmp_path, seed=test_case.seed, entry_count=test_case.entry_count)

    mismatches: tuple[str, ...] = snapshot_glob_mismatches(root=tmp_path)

    assert mismatches == test_case.expected_mismatches


@pytest.mark.parametrize(
    "test_case",
    [
        SharedSnapshotDiscoveryTestCase(
            "scoped_and_grouped_declarations",
            expected_model_paths=("models/orders.sql", "models/sales/daily.sql"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_shared_snapshot_when_discovering_project_then_matches_isolated_discovery(
    tmp_path: Path, test_case: SharedSnapshotDiscoveryTestCase
) -> None:
    write_scoped_project(root=tmp_path)

    mismatches: tuple[str, ...] = isolated_discovery_mismatches(project_dir=tmp_path)

    assert mismatches == test_case.expected_mismatches
    assert model_paths(inputs=discover_project_inputs(project_dir=tmp_path)) == (
        test_case.expected_model_paths
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DiscoveryPassRefreshTestCase(
            "added_and_removed_models",
            added_files={
                "models/sales/weekly.sql": "MODEL (description 'Weekly.');\nSELECT 1 AS week_id\n"
            },
            removed_path="models/orders.sql",
            expected_first_paths=("models/orders.sql", "models/sales/daily.sql"),
            expected_second_paths=("models/sales/daily.sql", "models/sales/weekly.sql"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_files_change_between_discovery_passes_when_discovering_then_sees_current_tree(
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    test_case: DiscoveryPassRefreshTestCase,
) -> None:
    write_scoped_project(root=tmp_path)
    first: tuple[str, ...] = model_paths(inputs=discover_project_inputs(project_dir=tmp_path))
    write_repo_files(tmp_path, test_case.added_files)
    (tmp_path / test_case.removed_path).unlink()

    second: tuple[str, ...] = model_paths(inputs=discover_project_inputs(project_dir=tmp_path))

    assert first == test_case.expected_first_paths
    assert second == test_case.expected_second_paths


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotScopeReuseTestCase(
            "nested_reuses_later_refreshes",
            expected_nested_reuse=True,
            expected_later_reuse=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_nested_scope_for_same_project_when_entering_then_reuses_active_snapshot(
    tmp_path: Path, test_case: SnapshotScopeReuseTestCase
) -> None:
    with DirectorySnapshot.scope(project_dir=tmp_path) as outer:
        with DirectorySnapshot.scope(project_dir=tmp_path) as inner:
            nested_reuse: bool = inner is outer
    with DirectorySnapshot.scope(project_dir=tmp_path) as later:
        later_reuse: bool = later is outer

    assert nested_reuse is test_case.expected_nested_reuse
    assert later_reuse is test_case.expected_later_reuse


@pytest.mark.parametrize(
    "test_case",
    [
        NativeHeaderMatchTestCase("seed_1", seed=1, count=2000),
        NativeHeaderMatchTestCase("seed_2", seed=2, count=2000),
        NativeHeaderMatchTestCase("seed_3", seed=3, count=2000),
        NativeHeaderMatchTestCase("seed_4", seed=4, count=2000),
    ],
    ids=lambda case: case.description,
)
def test_given_randomized_model_files_when_matching_natively_then_matches_python_pattern(
    test_case: NativeHeaderMatchTestCase,
) -> None:
    mismatches: tuple[str, ...] = header_match_mismatches(
        seed=test_case.seed, count=test_case.count
    )

    assert mismatches == test_case.expected_mismatches


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
