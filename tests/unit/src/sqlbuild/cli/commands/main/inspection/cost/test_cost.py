from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.cli.commands._helpers.cost.command import _parse_since_bound, run_cost_command
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cost.classes.run_cost_store import RunCostStore
from tests.unit.src.sqlbuild.cli.commands.main.inspection.cost._test_types import (
    CostCommandTestCase,
    CostRelativeSinceTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.inspection.cost.helpers import (
    build_cost_request,
    build_cost_run_record,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CostCommandTestCase(
            description="latest selector renders the latest record",
            expected_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_latest_selector_when_running_cost_then_latest_record_is_rendered(
    test_case: CostCommandTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    now: datetime = datetime(2026, 8, 23, tzinfo=UTC)
    RunCostStore.write(
        project_dir=tmp_path,
        record=build_cost_run_record(run_id="run-old", completed_at=now, usd="1"),
    )
    RunCostStore.write(
        project_dir=tmp_path,
        record=build_cost_run_record(
            run_id="run-new", completed_at=now + timedelta(minutes=1), usd="2"
        ),
    )

    exit_code: int = run_cost_command(build_cost_request(project_dir=tmp_path))

    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == test_case.expected_exit_code
    assert "Cost  $2.0000 estimated" in captured.out


@pytest.mark.parametrize(
    "test_case",
    [
        CostCommandTestCase(
            description="history date range includes the entire until date",
            expected_run_ids=("run-included",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_history_date_range_when_running_json_then_until_date_is_inclusive(
    test_case: CostCommandTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    RunCostStore.write(
        project_dir=tmp_path,
        record=build_cost_run_record(
            run_id="run-included",
            completed_at=datetime(2026, 8, 23, 23, 59, tzinfo=UTC),
            usd="1",
        ),
    )
    RunCostStore.write(
        project_dir=tmp_path,
        record=build_cost_run_record(
            run_id="run-excluded",
            completed_at=datetime(2026, 8, 24, tzinfo=UTC),
            usd="2",
        ),
    )

    run_cost_command(
        build_cost_request(
            project_dir=tmp_path,
            selector="history",
            until="2026-08-23",
            json_output=True,
        )
    )

    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert tuple(item["run_id"] for item in payload["runs"]) == test_case.expected_run_ids


@pytest.mark.parametrize(
    "test_case",
    [
        CostCommandTestCase(
            description="timezone-less history bound raises user error",
            expected_error_fragment="must include a timezone",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_timezone_less_history_bound_when_running_then_user_error_is_raised(
    test_case: CostCommandTestCase,
    tmp_path: Path,
) -> None:
    with pytest.raises(CliUserError, match=test_case.expected_error_fragment):
        run_cost_command(
            build_cost_request(
                project_dir=tmp_path,
                selector="history",
                since="2026-08-23T10:00:00",
            )
        )


@pytest.mark.parametrize(
    "test_case",
    [
        CostCommandTestCase(
            description="ambiguous run prefix raises user error",
            expected_error_fragment="ambiguous",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_ambiguous_prefix_when_running_cost_then_user_error_is_raised(
    test_case: CostCommandTestCase,
    tmp_path: Path,
) -> None:
    now: datetime = datetime(2026, 8, 23, tzinfo=UTC)
    RunCostStore.write(
        project_dir=tmp_path,
        record=build_cost_run_record(run_id="run-123", completed_at=now, usd="1"),
    )
    RunCostStore.write(
        project_dir=tmp_path,
        record=build_cost_run_record(
            run_id="run-456", completed_at=now + timedelta(seconds=1), usd="2"
        ),
    )

    with pytest.raises(CliUserError, match=test_case.expected_error_fragment):
        run_cost_command(build_cost_request(project_dir=tmp_path, selector="run-"))


@pytest.mark.parametrize(
    "test_case",
    [
        CostCommandTestCase(
            description="relative since bound filters history from the current UTC time",
            expected_run_ids=("run-recent",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_relative_since_bound_when_running_history_then_old_runs_are_excluded(
    test_case: CostCommandTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    now: datetime = datetime.now(UTC)
    RunCostStore.write(
        project_dir=tmp_path,
        record=build_cost_run_record(
            run_id="run-recent", completed_at=now - timedelta(days=6), usd="1"
        ),
    )
    RunCostStore.write(
        project_dir=tmp_path,
        record=build_cost_run_record(
            run_id="run-old", completed_at=now - timedelta(days=8), usd="2"
        ),
    )

    run_cost_command(
        build_cost_request(
            project_dir=tmp_path,
            selector="history",
            since="7d",
            json_output=True,
        )
    )

    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert tuple(item["run_id"] for item in payload["runs"]) == test_case.expected_run_ids
    assert payload["matching_count"] == len(test_case.expected_run_ids)


@pytest.mark.parametrize(
    "test_case",
    [
        CostRelativeSinceTestCase(
            description="days remain a valid relative bound",
            value="7d",
            expected_seconds=7 * 86_400,
        ),
        CostRelativeSinceTestCase(
            description="hours remain a valid relative bound",
            value="12h",
            expected_seconds=12 * 3_600,
        ),
        CostRelativeSinceTestCase(
            description="minutes remain a valid relative bound",
            value="90m",
            expected_seconds=90 * 60,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_supported_relative_since_duration_when_parsing_then_returns_expected_bound(
    test_case: CostRelativeSinceTestCase,
) -> None:
    before: datetime = datetime.now(UTC)
    result: datetime | None = _parse_since_bound(value=test_case.value)
    after: datetime = datetime.now(UTC)

    assert result is not None
    assert test_case.expected_seconds is not None
    assert before - timedelta(seconds=test_case.expected_seconds) <= result
    assert result <= after - timedelta(seconds=test_case.expected_seconds)


@pytest.mark.parametrize(
    "test_case",
    [
        CostRelativeSinceTestCase(
            description="seconds are explicitly unsupported",
            value="30s",
            expected_error_fragment="must use one of: d, h, m",
        ),
        CostRelativeSinceTestCase(
            description="calendar units are explicitly unsupported",
            value="1mo",
            expected_error_fragment="must use one of: d, h, m",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_relative_since_duration_when_parsing_then_raises_clear_error(
    test_case: CostRelativeSinceTestCase,
) -> None:
    assert test_case.expected_error_fragment is not None
    with pytest.raises(CliUserError, match=test_case.expected_error_fragment):
        _parse_since_bound(value=test_case.value)


@pytest.mark.parametrize(
    "test_case",
    [
        CostCommandTestCase(
            description="detail JSON uses the stable decimal-safe cost schema",
            expected_run_ids=("run-json",),
            expected_schema_version=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_json_detail_request_when_running_cost_then_stable_schema_is_emitted(
    test_case: CostCommandTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    now: datetime = datetime(2026, 8, 23, tzinfo=UTC)
    RunCostStore.write(
        project_dir=tmp_path,
        record=build_cost_run_record(
            run_id=test_case.expected_run_ids[0], completed_at=now, usd="2"
        ),
    )

    run_cost_command(
        build_cost_request(
            project_dir=tmp_path,
            selector="latest",
            json_output=True,
        )
    )

    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == test_case.expected_schema_version
    assert payload["run_id"] == test_case.expected_run_ids[0]
    assert payload["currency"] == "USD"
    assert payload["usd_per_credit"] == "3.00"
    assert isinstance(payload["totals"]["attributed_compute_credits"], str)
    assert "per_model" in payload
    assert "sql" not in payload


@pytest.mark.parametrize(
    "test_case",
    [
        CostCommandTestCase(
            description="detail JSON limit truncates models but preserves all-model totals",
            expected_run_ids=("run-limited",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_json_detail_limit_when_running_cost_then_models_only_are_truncated(
    test_case: CostCommandTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    now: datetime = datetime(2026, 8, 23, tzinfo=UTC)
    RunCostStore.write(
        project_dir=tmp_path,
        record=build_cost_run_record(
            run_id=test_case.expected_run_ids[0], completed_at=now, usd="2"
        ),
    )

    run_cost_command(
        build_cost_request(
            project_dir=tmp_path,
            selector="latest",
            limit=0,
            json_output=True,
        )
    )

    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert payload["per_model"] == []
    assert payload["totals"]["estimated_usd"] == "2"


@pytest.mark.parametrize(
    "test_case",
    [
        CostCommandTestCase(
            description="history metric ties use completion then ascending run ID",
            expected_run_ids=("run-new", "run-a", "run-b"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_equal_history_metrics_when_sorting_then_completion_and_run_id_break_ties(
    test_case: CostCommandTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    origin: datetime = datetime(2026, 8, 23, tzinfo=UTC)
    for run_id, completed_at in (
        ("run-b", origin),
        ("run-a", origin),
        ("run-new", origin + timedelta(minutes=1)),
    ):
        RunCostStore.write(
            project_dir=tmp_path,
            record=build_cost_run_record(
                run_id=run_id,
                completed_at=completed_at,
                usd="1",
            ),
        )

    run_cost_command(
        build_cost_request(
            project_dir=tmp_path,
            selector="history",
            sort="cost",
            order="desc",
            no_limit=True,
            json_output=True,
        )
    )

    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert tuple(run["run_id"] for run in payload["runs"]) == test_case.expected_run_ids
