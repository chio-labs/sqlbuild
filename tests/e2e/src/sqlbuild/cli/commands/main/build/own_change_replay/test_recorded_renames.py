"""E2E coverage: rename-rewritten references and inferred upstream columns never replay a model."""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build.own_change_replay._test_types import (
    OwnChangePlanBuildTestCase,
    UpstreamContractFailureTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.own_change_replay.helpers import (
    ENFORCED_CONTRACT_CONFIG,
    assert_plan_text,
    build,
    build_and_assert_rows,
    build_event_project,
    build_selected,
    build_star_project,
    direct_reference_merge_files,
    drop_upstream_column,
    incremental_upstream_files,
    plan_models,
    remove_downstream_declared_column,
    remove_migrate_from,
    rename_upstream_with_cli,
    udf_reference_merge_files,
)

_MERGE_ROWS: list[tuple[Any, ...]] = [
    (1, date(2026, 9, 1)),
    (2, date(2026, 9, 2)),
    (3, date(2026, 9, 3)),
]
_UDF_MERGE_ROWS: list[tuple[Any, ...]] = [
    (1, date(2026, 9, 1), 2),
    (2, date(2026, 9, 2), 3),
    (3, date(2026, 9, 3), 4),
]


@pytest.mark.parametrize(
    "test_case",
    [
        OwnChangePlanBuildTestCase(
            description="a UDF-calling downstream of a renamed upstream continues forward",
            expected_plan_fragments=("down_merge           merge (timestamp)",),
            unexpected_plan_fragments=("Query changed", "full rebuild", "S203"),
            expected_reasons={"down_merge": "normal_incremental"},
            expected_rows={"down_merge": _UDF_MERGE_ROWS},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_udf_downstream_when_upstream_is_renamed_then_downstream_continues_forward(
    test_case: OwnChangePlanBuildTestCase, tmp_path: Path
) -> None:
    project_dir: Path = build_event_project(
        tmp_path=tmp_path, extra_files=udf_reference_merge_files()
    )
    rename_upstream_with_cli(project_dir=project_dir, extra_sql="")

    assert_plan_text(
        project_dir=project_dir,
        expected=test_case.expected_plan_fragments,
        unexpected=test_case.unexpected_plan_fragments,
    )
    models: dict[str, dict[str, Any]] = plan_models(project_dir=project_dir)

    assert {name: models[name]["reason"] for name in test_case.expected_reasons} == (
        test_case.expected_reasons
    )
    build_and_assert_rows(project_dir=project_dir, expected_rows=test_case.expected_rows)
    assert plan_models(project_dir=project_dir)["down_merge"]["reason"] == "normal_incremental"


@pytest.mark.parametrize(
    "test_case",
    [
        OwnChangePlanBuildTestCase(
            description="incremental upstream renamed and built alone in an earlier run",
            expected_plan_fragments=("down_merge           merge (timestamp)",),
            unexpected_plan_fragments=("Query changed", "full rebuild", "S203"),
            expected_reasons={"down_merge": "normal_incremental"},
            expected_rows={"down_merge": _MERGE_ROWS},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_upstream_renamed_in_earlier_run_when_planning_then_downstream_continues_forward(
    test_case: OwnChangePlanBuildTestCase, tmp_path: Path
) -> None:
    project_dir: Path = build_event_project(
        tmp_path=tmp_path,
        extra_files={**incremental_upstream_files(), **direct_reference_merge_files()},
    )
    rename_upstream_with_cli(project_dir=project_dir, extra_sql="")
    build_selected(project_dir=project_dir, selector="upstream_renamed")

    assert_plan_text(
        project_dir=project_dir,
        expected=test_case.expected_plan_fragments,
        unexpected=test_case.unexpected_plan_fragments,
    )
    models: dict[str, dict[str, Any]] = plan_models(project_dir=project_dir)

    assert {name: models[name]["reason"] for name in test_case.expected_reasons} == (
        test_case.expected_reasons
    )
    build_and_assert_rows(project_dir=project_dir, expected_rows=test_case.expected_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        OwnChangePlanBuildTestCase(
            description="table renamed earlier and migrate_from removed afterwards",
            expected_plan_fragments=("down_merge           merge (timestamp)",),
            unexpected_plan_fragments=("Query changed", "full rebuild", "S203"),
            expected_reasons={"upstream_renamed": "no_change", "down_merge": "normal_incremental"},
            expected_rows={"down_merge": _MERGE_ROWS},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_migrate_from_removed_after_rename_when_planning_then_downstream_continues_forward(
    test_case: OwnChangePlanBuildTestCase, tmp_path: Path
) -> None:
    project_dir: Path = build_event_project(
        tmp_path=tmp_path, extra_files=direct_reference_merge_files()
    )
    rename_upstream_with_cli(project_dir=project_dir, extra_sql="")
    build_selected(project_dir=project_dir, selector="upstream_renamed")
    remove_migrate_from(project_dir=project_dir)

    assert_plan_text(
        project_dir=project_dir,
        expected=test_case.expected_plan_fragments,
        unexpected=test_case.unexpected_plan_fragments,
    )
    models: dict[str, dict[str, Any]] = plan_models(project_dir=project_dir)

    assert {name: models[name]["reason"] for name in test_case.expected_reasons} == (
        test_case.expected_reasons
    )
    build_and_assert_rows(project_dir=project_dir, expected_rows=test_case.expected_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        OwnChangePlanBuildTestCase(
            description="upstream drops a column a partial columns block does not declare",
            expected_plan_fragments=("Schema changed (1)", "down                 continue forward"),
            unexpected_plan_fragments=("full rebuild", "S203"),
            expected_reasons={"down": "schema_changed"},
            expected_rows={},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partial_columns_when_upstream_drops_undeclared_column_then_no_replay(
    test_case: OwnChangePlanBuildTestCase, tmp_path: Path
) -> None:
    project_dir: Path = build_star_project(
        tmp_path=tmp_path,
        downstream_config="  full_refresh false,\n  columns (\n    id (type INTEGER),\n  ),\n",
    )
    drop_upstream_column(project_dir=project_dir)

    assert_plan_text(
        project_dir=project_dir,
        expected=test_case.expected_plan_fragments,
        unexpected=test_case.unexpected_plan_fragments,
    )
    models: dict[str, dict[str, Any]] = plan_models(project_dir=project_dir)

    assert {name: models[name]["reason"] for name in test_case.expected_reasons} == (
        test_case.expected_reasons
    )
    assert models["down"]["backfill"] == {"action": "forward", "duration": None}


@pytest.mark.parametrize(
    "test_case",
    [
        UpstreamContractFailureTestCase(
            description="upstream drops a contract column of an unchanged model",
            expected_fragments=("K008", "runtime contract missing columns: event_date"),
            unexpected_fragments=("S203", "full rebuild"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unchanged_contract_model_when_upstream_drops_declared_column_then_build_fails(
    test_case: UpstreamContractFailureTestCase, tmp_path: Path
) -> None:
    project_dir: Path = build_star_project(
        tmp_path=tmp_path,
        downstream_config=f"  full_refresh false,\n{ENFORCED_CONTRACT_CONFIG}",
    )
    drop_upstream_column(project_dir=project_dir)

    assert_plan_text(
        project_dir=project_dir, expected=(), unexpected=test_case.unexpected_fragments
    )
    assert plan_models(project_dir=project_dir)["down"]["backfill"] == {
        "action": "forward",
        "duration": None,
    }
    result: subprocess.CompletedProcess[str] = build(project_dir=project_dir)
    output: str = result.stdout + result.stderr

    assert result.returncode != 0
    assert all(fragment in output for fragment in test_case.expected_fragments), output
    assert not any(fragment in output for fragment in test_case.unexpected_fragments), output


@pytest.mark.parametrize(
    "test_case",
    [
        OwnChangePlanBuildTestCase(
            description="own removal of a declared column follows replay_on_change full",
            expected_plan_fragments=("Query changed (1)", "down                 full rebuild"),
            unexpected_plan_fragments=("S203",),
            expected_reasons={"down": "query_changed"},
            expected_rows={},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_own_declared_column_removed_when_planning_then_own_replay_policy_applies(
    test_case: OwnChangePlanBuildTestCase, tmp_path: Path
) -> None:
    project_dir: Path = build_star_project(
        tmp_path=tmp_path, downstream_config=ENFORCED_CONTRACT_CONFIG
    )
    remove_downstream_declared_column(project_dir=project_dir)

    assert_plan_text(
        project_dir=project_dir,
        expected=test_case.expected_plan_fragments,
        unexpected=test_case.unexpected_plan_fragments,
    )
    models: dict[str, dict[str, Any]] = plan_models(project_dir=project_dir)

    assert {name: models[name]["reason"] for name in test_case.expected_reasons} == (
        test_case.expected_reasons
    )
    assert models["down"]["backfill"] == {"action": "full", "duration": None}


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
