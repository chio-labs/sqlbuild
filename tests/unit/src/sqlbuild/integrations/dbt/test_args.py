from __future__ import annotations

import pytest

from sqlbuild.integrations.dbt.exceptions import DbtInteropArgumentError
from sqlbuild.integrations.dbt.helpers.cli.arg_parser import parse_dbt_execution_args
from sqlbuild.integrations.dbt.helpers.cli.args import route_dbt_interop_args
from sqlbuild.integrations.dbt.models import DbtInteropParsedArgs, DbtInteropRoutedArgs
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtArgParseErrorTestCase,
    DbtArgParseTestCase,
    DbtArgRoutingErrorTestCase,
    DbtArgRoutingTestCase,
)

ROUTING_TEST_CASES: list[DbtArgRoutingTestCase] = [
    DbtArgRoutingTestCase(
        description="routes select and exclude only to dbt and combined selection",
        command="run",
        parsed=DbtInteropParsedArgs(
            select=("fact_orders", "tag:daily+"),
            exclude=("tag:deprecated",),
        ),
        expected_select=("fact_orders", "tag:daily+"),
        expected_exclude=("tag:deprecated",),
        expected_dbt_args=(
            "--select",
            "fact_orders",
            "tag:daily+",
            "--exclude",
            "tag:deprecated",
        ),
        expected_sqlbuild_args=(),
    ),
    DbtArgRoutingTestCase(
        description="routes shared vars full refresh threads and event time to both sides",
        command="run",
        parsed=DbtInteropParsedArgs(
            vars='{"run_date":"2026-01-01"}',
            full_refresh=True,
            threads="8",
            event_time_start="2024-09-01",
            event_time_end="2024-09-04",
        ),
        expected_select=(),
        expected_exclude=(),
        expected_dbt_args=(
            "--vars",
            '{"run_date":"2026-01-01"}',
            "--threads",
            "8",
            "--full-refresh",
            "--event-time-start",
            "2024-09-01",
            "--event-time-end",
            "2024-09-04",
        ),
        expected_sqlbuild_args=(
            "--vars",
            '{"run_date":"2026-01-01"}',
            "--concurrency",
            "8",
            "--full-refresh",
            "--start-cursor-ts",
            "2024-09-01",
            "--end-cursor-ts",
            "2024-09-04",
        ),
    ),
    DbtArgRoutingTestCase(
        description="routes shared vars full refresh and threads for build",
        command="build",
        parsed=DbtInteropParsedArgs(vars='{"batch":"daily"}', full_refresh=True, threads="4"),
        expected_select=(),
        expected_exclude=(),
        expected_dbt_args=("--vars", '{"batch":"daily"}', "--threads", "4", "--full-refresh"),
        expected_sqlbuild_args=(
            "--vars",
            '{"batch":"daily"}',
            "--concurrency",
            "4",
            "--full-refresh",
        ),
    ),
    DbtArgRoutingTestCase(
        description="passes full refresh to dbt only for test",
        command="test",
        parsed=DbtInteropParsedArgs(full_refresh=True),
        expected_select=(),
        expected_exclude=(),
        expected_dbt_args=("--full-refresh",),
        expected_sqlbuild_args=(),
    ),
    DbtArgRoutingTestCase(
        description="passes event time to dbt only for test",
        command="test",
        parsed=DbtInteropParsedArgs(
            event_time_start="2024-09-01",
            event_time_end="2024-09-04",
        ),
        expected_select=(),
        expected_exclude=(),
        expected_dbt_args=(
            "--event-time-start",
            "2024-09-01",
            "--event-time-end",
            "2024-09-04",
        ),
        expected_sqlbuild_args=(),
    ),
    DbtArgRoutingTestCase(
        description="passes vars and threads to both sides for test",
        command="test",
        parsed=DbtInteropParsedArgs(vars='{"suite":"nightly"}', threads="3"),
        expected_select=(),
        expected_exclude=(),
        expected_dbt_args=("--vars", '{"suite":"nightly"}', "--threads", "3"),
        expected_sqlbuild_args=("--vars", '{"suite":"nightly"}', "--concurrency", "3"),
    ),
    DbtArgRoutingTestCase(
        description="routes dbt project runtime flags only to dbt",
        command="build",
        parsed=DbtInteropParsedArgs(
            project_dir="dbt",
            profiles_dir="profiles",
            profile="analytics",
            target="prod",
            target_path="target/dbt",
            state="state",
            defer=True,
            indirect_selection="eager",
        ),
        expected_select=(),
        expected_exclude=(),
        expected_dbt_args=(
            "--project-dir",
            "dbt",
            "--profiles-dir",
            "profiles",
            "--profile",
            "analytics",
            "--target",
            "prod",
            "--target-path",
            "target/dbt",
            "--state",
            "state",
            "--indirect-selection",
            "eager",
            "--defer",
        ),
        expected_sqlbuild_args=(),
    ),
    DbtArgRoutingTestCase(
        description="routes SQLBuild cursor and defer overrides to SQLBuild only",
        command="run",
        parsed=DbtInteropParsedArgs(
            start_cursor_int="100",
            end_cursor_int="200",
            defer_to="prod",
        ),
        expected_select=(),
        expected_exclude=(),
        expected_dbt_args=(),
        expected_sqlbuild_args=(
            "--start-cursor-int",
            "100",
            "--end-cursor-int",
            "200",
            "--defer-to",
            "prod",
        ),
    ),
    DbtArgRoutingTestCase(
        description="routes SQLBuild timestamp cursor overrides for plan",
        command="plan",
        parsed=DbtInteropParsedArgs(start_cursor_ts="2024-01-01", end_cursor_ts="2024-01-02"),
        expected_select=(),
        expected_exclude=(),
        expected_dbt_args=(),
        expected_sqlbuild_args=(
            "--start-cursor-ts",
            "2024-01-01",
            "--end-cursor-ts",
            "2024-01-02",
        ),
    ),
    DbtArgRoutingTestCase(
        description="routes SQLBuild integer cursor overrides for build",
        command="build",
        parsed=DbtInteropParsedArgs(start_cursor_int="10", end_cursor_int="20"),
        expected_select=(),
        expected_exclude=(),
        expected_dbt_args=(),
        expected_sqlbuild_args=("--start-cursor-int", "10", "--end-cursor-int", "20"),
    ),
    DbtArgRoutingTestCase(
        description="routes SQLBuild defer override for plan",
        command="plan",
        parsed=DbtInteropParsedArgs(defer_to="prod"),
        expected_select=(),
        expected_exclude=(),
        expected_dbt_args=(),
        expected_sqlbuild_args=("--defer-to", "prod"),
    ),
    DbtArgRoutingTestCase(
        description="routes SQLBuild execution bool flags for run",
        command="run",
        parsed=DbtInteropParsedArgs(fail_fast=True),
        expected_select=(),
        expected_exclude=(),
        expected_dbt_args=(),
        expected_sqlbuild_args=("--fail-fast",),
    ),
    DbtArgRoutingTestCase(
        description="routes SQLBuild force flag for build",
        command="build",
        parsed=DbtInteropParsedArgs(force=True),
        expected_select=(),
        expected_exclude=(),
        expected_dbt_args=(),
        expected_sqlbuild_args=("--force",),
    ),
    DbtArgRoutingTestCase(
        description="routes dbt defer clone flag to wrapper only",
        command="build",
        parsed=DbtInteropParsedArgs(defer_clone_from=True),
        expected_select=(),
        expected_exclude=(),
        expected_dbt_args=(),
        expected_sqlbuild_args=(),
        expected_defer_clone_from=True,
    ),
    DbtArgRoutingTestCase(
        description="appends dbt passthrough tail to dbt args verbatim",
        command="test",
        parsed=DbtInteropParsedArgs(
            select=("fct_orders",),
            dbt_passthrough=("--store-failures", "--favor-state"),
        ),
        expected_select=("fct_orders",),
        expected_exclude=(),
        expected_dbt_args=(
            "--select",
            "fct_orders",
            "--store-failures",
            "--favor-state",
        ),
        expected_sqlbuild_args=(),
    ),
    DbtArgRoutingTestCase(
        description="routes event time with SQLBuild integer cursors without conflict",
        command="run",
        parsed=DbtInteropParsedArgs(
            event_time_start="2024-09-01",
            event_time_end="2024-09-04",
            start_cursor_int="10",
            end_cursor_int="20",
        ),
        expected_select=(),
        expected_exclude=(),
        expected_dbt_args=(
            "--event-time-start",
            "2024-09-01",
            "--event-time-end",
            "2024-09-04",
        ),
        expected_sqlbuild_args=(
            "--start-cursor-ts",
            "2024-09-01",
            "--end-cursor-ts",
            "2024-09-04",
            "--start-cursor-int",
            "10",
            "--end-cursor-int",
            "20",
        ),
    ),
]

ROUTING_ERROR_TEST_CASES: list[DbtArgRoutingErrorTestCase] = [
    DbtArgRoutingErrorTestCase(
        description="rejects event time start without end",
        command="run",
        parsed=DbtInteropParsedArgs(event_time_start="2024-09-01"),
        expected_error_fragment="must be provided together",
    ),
    DbtArgRoutingErrorTestCase(
        description="rejects event time end without start",
        command="run",
        parsed=DbtInteropParsedArgs(event_time_end="2024-09-04"),
        expected_error_fragment="must be provided together",
    ),
    DbtArgRoutingErrorTestCase(
        description="rejects event time with SQLBuild timestamp cursor",
        command="run",
        parsed=DbtInteropParsedArgs(
            event_time_start="2024-09-01",
            event_time_end="2024-09-04",
            start_cursor_ts="2024-09-02",
        ),
        expected_error_fragment="conflict with --start-cursor-ts/end-cursor-ts",
    ),
    DbtArgRoutingErrorTestCase(
        description="rejects unsupported SQLBuild hard copy option on run",
        command="run",
        parsed=DbtInteropParsedArgs(hard_copy=True),
        expected_error_fragment="is not a valid SQLBuild option",
    ),
    DbtArgRoutingErrorTestCase(
        description="rejects run-only SQLBuild execution flag on plan",
        command="plan",
        parsed=DbtInteropParsedArgs(fail_fast=True),
        expected_error_fragment="is not a valid SQLBuild option",
    ),
    DbtArgRoutingErrorTestCase(
        description="rejects run cursor option on test",
        command="test",
        parsed=DbtInteropParsedArgs(start_cursor_int="1"),
        expected_error_fragment="is not a valid SQLBuild option",
    ),
    DbtArgRoutingErrorTestCase(
        description="rejects defer clone with defer to",
        command="build",
        parsed=DbtInteropParsedArgs(defer_to="prod", defer_clone_from=True),
        expected_error_fragment="cannot be used with --defer-to",
    ),
    DbtArgRoutingErrorTestCase(
        description="rejects defer clone on plan",
        command="plan",
        parsed=DbtInteropParsedArgs(defer_clone_from=True),
        expected_error_fragment="is not a valid SQLBuild option",
    ),
]

PARSE_TEST_CASES: list[DbtArgParseTestCase] = [
    DbtArgParseTestCase(
        description="parses select full refresh and dbt passthrough after separator",
        command="build",
        args=("--select", "fact_orders", "--full-refresh", "--", "--log-level", "debug"),
        expected_select=("fact_orders",),
        expected_exclude=(),
        expected_full_refresh=True,
        expected_target=None,
        expected_dbt_passthrough=("--log-level", "debug"),
    ),
    DbtArgParseTestCase(
        description="parses dbt selector values and target before separator",
        command="run",
        args=("--select", "state:modified+", "--target", "prod"),
        expected_select=("state:modified+",),
        expected_exclude=(),
        expected_full_refresh=False,
        expected_target="prod",
        expected_dbt_passthrough=(),
    ),
    DbtArgParseTestCase(
        description="parses short select alias and exclude",
        command="build",
        args=("-s", "stg_orders", "--select", "fact_orders+", "--exclude", "tag:old"),
        expected_select=("stg_orders", "fact_orders+"),
        expected_exclude=("tag:old",),
        expected_full_refresh=False,
        expected_target=None,
        expected_dbt_passthrough=(),
    ),
    DbtArgParseTestCase(
        description="parses valueless defer clone flag",
        command="build",
        args=("--defer-clone-from", "--select", "fact_orders"),
        expected_select=("fact_orders",),
        expected_exclude=(),
        expected_full_refresh=False,
        expected_target=None,
        expected_dbt_passthrough=(),
        expected_defer_clone_from=True,
    ),
]

PARSE_ERROR_TEST_CASES: list[DbtArgParseErrorTestCase] = [
    DbtArgParseErrorTestCase(
        description="rejects mistyped leading flag before separator",
        command="build",
        args=("--slect", "fact_orders"),
        expected_error_fragment="unrecognized option",
    ),
    DbtArgParseErrorTestCase(
        description="rejects missing value for declared flag",
        command="run",
        args=("--target",),
        expected_error_fragment="expected one argument",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ROUTING_TEST_CASES,
    ids=[case.description for case in ROUTING_TEST_CASES],
)
def test_given_parsed_dbt_args_when_routing_then_returns_expected_buckets(
    test_case: DbtArgRoutingTestCase,
) -> None:
    result: DbtInteropRoutedArgs = route_dbt_interop_args(
        command=test_case.command,
        parsed=test_case.parsed,
    )

    assert result.command == test_case.command
    assert result.select == test_case.expected_select
    assert result.exclude == test_case.expected_exclude
    assert result.dbt_args == test_case.expected_dbt_args
    assert result.sqlbuild_args == test_case.expected_sqlbuild_args
    assert result.defer_clone_from == test_case.expected_defer_clone_from


@pytest.mark.parametrize(
    "test_case",
    ROUTING_ERROR_TEST_CASES,
    ids=[case.description for case in ROUTING_ERROR_TEST_CASES],
)
def test_given_invalid_parsed_dbt_args_when_routing_then_raises_clear_error(
    test_case: DbtArgRoutingErrorTestCase,
) -> None:
    with pytest.raises(DbtInteropArgumentError, match=test_case.expected_error_fragment):
        route_dbt_interop_args(command=test_case.command, parsed=test_case.parsed)


@pytest.mark.parametrize(
    "test_case",
    PARSE_TEST_CASES,
    ids=[case.description for case in PARSE_TEST_CASES],
)
def test_given_raw_dbt_tokens_when_parsing_then_returns_declared_flags(
    test_case: DbtArgParseTestCase,
) -> None:
    parsed: DbtInteropParsedArgs = parse_dbt_execution_args(
        command=DbtInteropCommand(test_case.command),
        args=test_case.args,
    )

    assert parsed.select == test_case.expected_select
    assert parsed.exclude == test_case.expected_exclude
    assert parsed.full_refresh == test_case.expected_full_refresh
    assert parsed.target == test_case.expected_target
    assert parsed.dbt_passthrough == test_case.expected_dbt_passthrough
    assert parsed.defer_clone_from == test_case.expected_defer_clone_from


@pytest.mark.parametrize(
    "test_case",
    PARSE_ERROR_TEST_CASES,
    ids=[case.description for case in PARSE_ERROR_TEST_CASES],
)
def test_given_invalid_raw_dbt_tokens_when_parsing_then_raises_clear_error(
    test_case: DbtArgParseErrorTestCase,
) -> None:
    with pytest.raises(DbtInteropArgumentError, match=test_case.expected_error_fragment):
        parse_dbt_execution_args(
            command=DbtInteropCommand(test_case.command),
            args=test_case.args,
        )
