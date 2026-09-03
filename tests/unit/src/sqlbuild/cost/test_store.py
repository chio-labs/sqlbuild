from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sqlbuild.cost.classes.run_cost_store import RunCostStore
from sqlbuild.cost.exceptions import CostArtifactError
from sqlbuild.cost.models import CostRunRecord
from tests.unit.src.sqlbuild.cost._test_types import (
    CostStoreTestCase,
    InvalidCostArtifactTestCase,
    InvalidCostRunIdTestCase,
)
from tests.unit.src.sqlbuild.cost.helpers import build_cost_run_record


@pytest.mark.parametrize(
    "test_case",
    [
        CostStoreTestCase(
            description="written cost run round trips exact decimals",
            expected_run_ids=("run-123",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cost_run_when_writing_then_record_round_trips_exact_decimals(
    test_case: CostStoreTestCase, tmp_path: Path
) -> None:
    record: CostRunRecord = build_cost_run_record(
        run_id=test_case.expected_run_ids[0],
        completed_at=datetime(2026, 8, 23, tzinfo=UTC),
    )

    path: Path = RunCostStore.write(project_dir=tmp_path, record=record)

    assert path == (tmp_path / "target" / "executions" / test_case.expected_run_ids[0] / "run.json")
    assert RunCostStore.read(project_dir=tmp_path, run_id=test_case.expected_run_ids[0]) == record
    assert not (path.parent / ".run.json.tmp").exists()


@pytest.mark.parametrize(
    "test_case",
    [
        CostStoreTestCase(
            description="listing orders latest completion first",
            expected_run_ids=("run-new", "run-old"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_multiple_cost_runs_when_listing_then_latest_completion_is_first(
    test_case: CostStoreTestCase, tmp_path: Path
) -> None:
    origin: datetime = datetime(2026, 8, 23, tzinfo=UTC)
    older: CostRunRecord = build_cost_run_record(run_id="run-old", completed_at=origin)
    latest: CostRunRecord = build_cost_run_record(
        run_id="run-new", completed_at=origin + timedelta(minutes=1)
    )
    RunCostStore.write(project_dir=tmp_path, record=older)
    RunCostStore.write(project_dir=tmp_path, record=latest)

    records: tuple[CostRunRecord, ...] = RunCostStore.list(project_dir=tmp_path)

    assert tuple(record.run_id for record in records) == test_case.expected_run_ids
    assert records == (latest, older)
    assert RunCostStore.resolve(project_dir=tmp_path, selector="latest") == latest
    assert RunCostStore.resolve(project_dir=tmp_path, selector="run-o") == older


@pytest.mark.parametrize(
    "test_case",
    [
        InvalidCostArtifactTestCase(
            description="naive timestamp artifact is isolated from valid history",
            old_fragment='"completed_at": "2026-08-23T00:00:00+00:00"',
            new_fragment='"completed_at": "2026-08-23T00:00:00"',
            expected_run_ids=("run-valid",),
        ),
        InvalidCostArtifactTestCase(
            description="forward schema version is isolated from valid history",
            old_fragment='"version": 1',
            new_fragment='"version": 2',
            expected_run_ids=("run-valid",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_artifact_when_listing_then_valid_history_remains_available(
    test_case: InvalidCostArtifactTestCase,
    tmp_path: Path,
) -> None:
    completed_at: datetime = datetime(2026, 8, 23, tzinfo=UTC)
    RunCostStore.write(
        project_dir=tmp_path,
        record=build_cost_run_record(run_id="run-valid", completed_at=completed_at),
    )
    invalid_path: Path = RunCostStore.write(
        project_dir=tmp_path,
        record=build_cost_run_record(run_id="run-invalid", completed_at=completed_at),
    )
    invalid_path.write_text(
        invalid_path.read_text(encoding="utf-8").replace(
            test_case.old_fragment,
            test_case.new_fragment,
            1,
        ),
        encoding="utf-8",
    )

    records: tuple[CostRunRecord, ...] = RunCostStore.list(project_dir=tmp_path)

    assert tuple(record.run_id for record in records) == test_case.expected_run_ids


@pytest.mark.parametrize(
    "test_case",
    [
        InvalidCostRunIdTestCase(
            description="parent traversal run ID is rejected",
            run_id="../../outside",
            expected_error_fragment="one path component",
        ),
        InvalidCostRunIdTestCase(
            description="absolute run ID is rejected",
            run_id="/tmp/outside",
            expected_error_fragment="one path component",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsafe_run_id_when_reading_then_path_escape_is_rejected(
    test_case: InvalidCostRunIdTestCase,
    tmp_path: Path,
) -> None:
    with pytest.raises(CostArtifactError, match=test_case.expected_error_fragment):
        RunCostStore.read(project_dir=tmp_path, run_id=test_case.run_id)


@pytest.mark.parametrize(
    "test_case",
    [
        CostStoreTestCase(
            description="ambiguous run prefix resolves to none",
            expected_run_ids=("run-123", "run-456"),
            expected_resolved=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_ambiguous_run_prefix_when_resolving_then_none_is_returned(
    test_case: CostStoreTestCase, tmp_path: Path
) -> None:
    origin: datetime = datetime(2026, 8, 23, tzinfo=UTC)
    RunCostStore.write(
        project_dir=tmp_path,
        record=build_cost_run_record(run_id=test_case.expected_run_ids[0], completed_at=origin),
    )
    RunCostStore.write(
        project_dir=tmp_path,
        record=build_cost_run_record(
            run_id=test_case.expected_run_ids[1],
            completed_at=origin + timedelta(minutes=1),
        ),
    )

    resolved: CostRunRecord | None = RunCostStore.resolve(project_dir=tmp_path, selector="run-")
    assert (resolved is not None) is test_case.expected_resolved


@pytest.mark.parametrize(
    "test_case",
    [
        CostStoreTestCase(
            description="latest skips a newer non-terminal started record",
            expected_run_ids=("run-complete",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_newer_running_record_when_resolving_latest_then_terminal_run_is_returned(
    test_case: CostStoreTestCase,
    tmp_path: Path,
) -> None:
    origin: datetime = datetime(2026, 8, 23, tzinfo=UTC)
    completed: CostRunRecord = build_cost_run_record(
        run_id=test_case.expected_run_ids[0], completed_at=origin
    )
    running: CostRunRecord = replace(
        build_cost_run_record(run_id="run-running", completed_at=origin + timedelta(minutes=1)),
        build_status="running",
    )
    RunCostStore.write(project_dir=tmp_path, record=completed)
    RunCostStore.write(project_dir=tmp_path, record=running)

    resolved: CostRunRecord | None = RunCostStore.resolve(project_dir=tmp_path, selector="latest")

    assert resolved == completed


@pytest.mark.parametrize(
    "test_case",
    [
        CostStoreTestCase(
            description="malformed decimal artifact is isolated from valid history",
            expected_run_ids=("run-valid",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_malformed_decimal_artifact_when_listing_then_valid_runs_remain_available(
    test_case: CostStoreTestCase,
    tmp_path: Path,
) -> None:
    origin: datetime = datetime(2026, 8, 23, tzinfo=UTC)
    valid: CostRunRecord = build_cost_run_record(
        run_id=test_case.expected_run_ids[0], completed_at=origin
    )
    invalid: CostRunRecord = build_cost_run_record(
        run_id="run-invalid", completed_at=origin + timedelta(minutes=1)
    )
    RunCostStore.write(project_dir=tmp_path, record=valid)
    invalid_path: Path = RunCostStore.write(project_dir=tmp_path, record=invalid)
    invalid_path.write_text(
        invalid_path.read_text(encoding="utf-8").replace('"3.00"', '"not-a-decimal"', 1),
        encoding="utf-8",
    )

    records: tuple[CostRunRecord, ...] = RunCostStore.list(project_dir=tmp_path)

    assert tuple(record.run_id for record in records) == test_case.expected_run_ids
