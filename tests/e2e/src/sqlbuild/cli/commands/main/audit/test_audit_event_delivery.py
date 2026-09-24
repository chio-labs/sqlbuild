"""E2E coverage for incremental audit lifecycle delivery and sink drain accounting."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.audit._test_types import (
    IncrementalAuditEventE2ETestCase,
    InvalidDrainTimeoutE2ETestCase,
    SlowSinkDropE2ETestCase,
    SlowSinkFullDeliveryE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.audit.helpers import (
    delivery_model_files,
    delivery_project_toml,
    events_of_type,
    read_sequenced_events,
    recording_sink_source,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)

_WARNING_PATTERN: re.Pattern[str] = re.compile(
    r"Warning: command completed successfully, but lifecycle event export was incomplete: "
    r"(?P<dropped>\d+) of (?P<accepted>\d+) events dropped, (?P<failed>\d+) failed "
    r"\(sink 'slow_orders_events'\)\. "
    r"Increase sinks\.lifecycle\.shutdown_timeout or check sink health\."
)


@pytest.mark.parametrize(
    "test_case",
    (
        IncrementalAuditEventE2ETestCase(
            "serial audit command",
            ("build", "--no-audits"),
            ("audit", "--concurrency", "1"),
            13,
        ),
        IncrementalAuditEventE2ETestCase(
            "concurrent audit command",
            ("build", "--no-audits"),
            ("audit", "--concurrency", "3"),
            13,
        ),
        IncrementalAuditEventE2ETestCase("build with model audits", ("compile",), ("build",), 13),
    ),
    ids=lambda case: case.description,
)
def test_given_many_audits_when_running_then_audit_completed_events_arrive_during_execution(
    test_case: IncrementalAuditEventE2ETestCase,
    tmp_path: Path,
) -> None:
    event_path: Path = tmp_path / "orders-events.jsonl"
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="audit_event_delivery",
        repo_files={
            "sqlbuild_project.toml": delivery_project_toml(lifecycle_config=""),
            **delivery_model_files(),
            "sinks/orders_events.py": recording_sink_source(
                event_kinds="{LifecycleEventKind.AUDIT, LifecycleEventKind.RESOURCE}",
                delay_seconds=0,
            ),
        },
    )
    setup: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", *test_case.setup_command),
        project_dir=project_dir,
        env={"ORDERS_EVENT_PATH": str(tmp_path / "setup-events.jsonl")},
    )
    assert setup.returncode == 0, setup.stdout + setup.stderr

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", *test_case.command),
        project_dir=project_dir,
        env={"ORDERS_EVENT_PATH": str(event_path)},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "event export was incomplete" not in result.stderr
    events: list[dict[str, object]] = read_sequenced_events(event_path)
    audit_events: list[dict[str, object]] = events_of_type(events, "audit_completed")
    resource_starts: list[dict[str, object]] = events_of_type(events, "resource_attempt_started")
    result_ids: set[str] = {
        str(json.loads(json.dumps(event["payload"]))["result_id"]) for event in audit_events
    }
    persisted: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "audit_event_delivery.duckdb",
        sql=(
            "SELECT result_id FROM main._sqlbuild_audit_results "
            f"WHERE invocation_id = '{audit_events[0]['invocation_id']}'"
        ),
    )
    assert len(audit_events) == test_case.expected_audit_count
    assert len(result_ids) == test_case.expected_audit_count
    assert {str(row[0]) for row in persisted} == result_ids
    assert int(str(audit_events[0]["invocation_sequence"])) < int(
        str(resource_starts[-1]["invocation_sequence"])
    )
    assert {event["resource_id"] for event in audit_events} == {None}


@pytest.mark.parametrize(
    "test_case",
    (SlowSinkDropE2ETestCase("zero drain drops queued events", "0s", 13),),
    ids=lambda case: case.description,
)
def test_given_slow_sink_and_zero_drain_when_auditing_then_warns_with_counts_and_succeeds(
    test_case: SlowSinkDropE2ETestCase,
    tmp_path: Path,
) -> None:
    event_path: Path = tmp_path / "orders-events.jsonl"
    event_path.touch()
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="audit_event_delivery",
        repo_files={
            "sqlbuild_project.toml": delivery_project_toml(
                lifecycle_config=(
                    f'\n[sinks.lifecycle]\nshutdown_timeout = "{test_case.shutdown_timeout}"\n'
                )
            ),
            **delivery_model_files(),
            "sinks/orders_events.py": recording_sink_source(
                event_kinds="{LifecycleEventKind.AUDIT}", delay_seconds=0.4
            ),
        },
    )
    setup: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--no-audits"),
        project_dir=project_dir,
        env={"ORDERS_EVENT_PATH": str(tmp_path / "setup-events.jsonl")},
    )
    assert setup.returncode == 0, setup.stdout + setup.stderr

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "audit", "--concurrency", "1", "--json"),
        project_dir=project_dir,
        env={"ORDERS_EVENT_PATH": str(event_path)},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload: dict[str, object] = json.loads(result.stdout)
    match: re.Match[str] | None = _WARNING_PATTERN.search(result.stderr)
    assert match is not None, result.stderr
    dropped: int = int(match.group("dropped"))
    failed: int = int(match.group("failed"))
    delivered_lines: int = len(read_sequenced_events(event_path))
    assert payload["summary"] is not None
    assert int(match.group("accepted")) == test_case.expected_accepted
    assert dropped + failed > 0
    assert test_case.expected_accepted - dropped - failed <= delivered_lines
    assert delivered_lines <= test_case.expected_accepted - dropped
    assert result.stderr.count("event export was incomplete") == 1


@pytest.mark.parametrize(
    "test_case",
    (SlowSinkFullDeliveryE2ETestCase("raised drain delivers every event", "60s", 13),),
    ids=lambda case: case.description,
)
def test_given_slow_sink_and_raised_drain_when_auditing_then_delivers_all_without_warning(
    test_case: SlowSinkFullDeliveryE2ETestCase,
    tmp_path: Path,
) -> None:
    event_path: Path = tmp_path / "orders-events.jsonl"
    event_path.touch()
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="audit_event_delivery",
        repo_files={
            "sqlbuild_project.toml": delivery_project_toml(
                lifecycle_config=(
                    f'\n[sinks.lifecycle]\nshutdown_timeout = "{test_case.shutdown_timeout}"\n'
                )
            ),
            **delivery_model_files(),
            "sinks/orders_events.py": recording_sink_source(
                event_kinds="{LifecycleEventKind.AUDIT}", delay_seconds=0.4
            ),
        },
    )
    setup: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--no-audits"),
        project_dir=project_dir,
        env={"ORDERS_EVENT_PATH": str(tmp_path / "setup-events.jsonl")},
    )
    assert setup.returncode == 0, setup.stdout + setup.stderr

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "audit", "--concurrency", "1", "--json"),
        project_dir=project_dir,
        env={"ORDERS_EVENT_PATH": str(event_path)},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["summary"] is not None
    assert "event export was incomplete" not in result.stderr
    assert len(read_sequenced_events(event_path)) == test_case.expected_delivered


@pytest.mark.parametrize(
    "test_case",
    (
        InvalidDrainTimeoutE2ETestCase(
            "negative duration",
            '"-5s"',
            "sinks.lifecycle.shutdown_timeout must be a fixed duration from '0s' to '10m'",
        ),
        InvalidDrainTimeoutE2ETestCase(
            "bare number",
            "5",
            "sinks.lifecycle.shutdown_timeout must be a fixed duration from '0s' to '10m'",
        ),
        InvalidDrainTimeoutE2ETestCase(
            "above upper bound",
            '"1h"',
            "sinks.lifecycle.shutdown_timeout must be a fixed duration from '0s' to '10m'",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_drain_timeout_when_auditing_then_fails_with_config_error(
    test_case: InvalidDrainTimeoutE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="audit_event_delivery",
        repo_files={
            "sqlbuild_project.toml": delivery_project_toml(
                lifecycle_config=(
                    f"\n[sinks.lifecycle]\nshutdown_timeout = {test_case.shutdown_timeout_toml}\n"
                )
            ),
            **delivery_model_files(),
            "sinks/orders_events.py": recording_sink_source(
                event_kinds="{LifecycleEventKind.AUDIT}", delay_seconds=0
            ),
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "audit"),
        project_dir=project_dir,
        env={"ORDERS_EVENT_PATH": str(tmp_path / "orders-events.jsonl")},
    )

    assert result.returncode != 0
    assert test_case.expected_error in result.stdout + result.stderr


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
