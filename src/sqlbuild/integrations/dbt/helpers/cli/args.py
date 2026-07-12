"""Argument routing helpers for `sqb dbt` commands."""

from __future__ import annotations

from sqlbuild.integrations.dbt.exceptions import DbtInteropArgumentError
from sqlbuild.integrations.dbt.models import DbtInteropParsedArgs, DbtInteropRoutedArgs
from sqlbuild.integrations.dbt.types import DbtInteropCommand


def route_dbt_interop_args(
    *, command: DbtInteropCommand | str, parsed: DbtInteropParsedArgs
) -> DbtInteropRoutedArgs:
    """Split parsed `sqb dbt <command>` flags into dbt and SQLBuild buckets."""

    try:
        normalized_command: DbtInteropCommand = DbtInteropCommand(command)
    except ValueError as exc:
        raise DbtInteropArgumentError(
            f"Unsupported sqb dbt command: {command}",
            code="C236",
        ) from exc
    _validate_event_time_pair(parsed)
    _validate_defer_clone_conflict(parsed)
    _validate_sqlbuild_flags_allowed(command=normalized_command, parsed=parsed)
    dbt_args: list[str] = []
    sqlbuild_args: list[str] = []
    dbt_args = _route_selection(parsed=parsed, dbt_args=dbt_args)
    dbt_args, sqlbuild_args = _route_shared(
        command=normalized_command, parsed=parsed, dbt_args=dbt_args, sqlbuild_args=sqlbuild_args
    )
    dbt_args = _route_dbt_config(parsed=parsed, dbt_args=dbt_args)
    sqlbuild_args = _route_sqlbuild_only(parsed=parsed, sqlbuild_args=sqlbuild_args)
    _validate_event_time_cursor_conflict(command=normalized_command, parsed=parsed)
    dbt_args.extend(parsed.dbt_passthrough)
    return DbtInteropRoutedArgs(
        command=normalized_command,
        select=tuple(parsed.select),
        exclude=tuple(parsed.exclude),
        dbt_args=tuple(dbt_args),
        sqlbuild_args=tuple(sqlbuild_args),
        defer_clone_from=parsed.defer_clone_from,
    )


def _route_selection(*, parsed: DbtInteropParsedArgs, dbt_args: list[str]) -> list[str]:
    if parsed.select:
        dbt_args.extend(("--select", *parsed.select))
    if parsed.exclude:
        dbt_args.extend(("--exclude", *parsed.exclude))
    return dbt_args


def _route_shared(
    *,
    command: DbtInteropCommand,
    parsed: DbtInteropParsedArgs,
    dbt_args: list[str],
    sqlbuild_args: list[str],
) -> tuple[list[str], list[str]]:
    if parsed.vars is not None:
        dbt_args.extend(("--vars", parsed.vars))
        sqlbuild_args.extend(("--vars", parsed.vars))
    if parsed.threads is not None:
        dbt_args.extend(("--threads", parsed.threads))
        sqlbuild_args.extend(("--concurrency", parsed.threads))
    if parsed.full_refresh:
        dbt_args.append("--full-refresh")
        if _map_full_refresh_to_sqlbuild(command):
            sqlbuild_args.append("--full-refresh")
    if parsed.event_time_start is not None:
        dbt_args.extend(("--event-time-start", parsed.event_time_start))
        if _map_event_time_to_sqlbuild(command):
            sqlbuild_args.extend(("--start-cursor-ts", parsed.event_time_start))
    if parsed.event_time_end is not None:
        dbt_args.extend(("--event-time-end", parsed.event_time_end))
        if _map_event_time_to_sqlbuild(command):
            sqlbuild_args.extend(("--end-cursor-ts", parsed.event_time_end))
    return dbt_args, sqlbuild_args


def _route_dbt_config(*, parsed: DbtInteropParsedArgs, dbt_args: list[str]) -> list[str]:
    for flag, value in (
        ("--project-dir", parsed.project_dir),
        ("--profiles-dir", parsed.profiles_dir),
        ("--profile", parsed.profile),
        ("--target", parsed.target),
        ("--target-path", parsed.target_path),
        ("--state", parsed.state),
        ("--indirect-selection", parsed.indirect_selection),
    ):
        if value is not None:
            dbt_args.extend((flag, value))
    if parsed.defer:
        dbt_args.append("--defer")
    return dbt_args


def _route_sqlbuild_only(*, parsed: DbtInteropParsedArgs, sqlbuild_args: list[str]) -> list[str]:
    for flag, value in (
        ("--start-cursor-ts", parsed.start_cursor_ts),
        ("--end-cursor-ts", parsed.end_cursor_ts),
        ("--start-cursor-int", parsed.start_cursor_int),
        ("--end-cursor-int", parsed.end_cursor_int),
        ("--defer-to", parsed.defer_to),
    ):
        if value is not None:
            sqlbuild_args.extend((flag, value))
    for flag, enabled in (
        ("--fail-fast", parsed.fail_fast),
        ("--force", parsed.force),
        ("--hard-copy", parsed.hard_copy),
    ):
        if enabled:
            sqlbuild_args.append(flag)
    return sqlbuild_args


def _validate_event_time_pair(parsed: DbtInteropParsedArgs) -> None:
    if (parsed.event_time_start is None) == (parsed.event_time_end is None):
        return
    raise DbtInteropArgumentError(
        "--event-time-start and --event-time-end must be provided together",
        code="C233",
    )


def _validate_defer_clone_conflict(parsed: DbtInteropParsedArgs) -> None:
    if parsed.defer_to is None or not parsed.defer_clone_from:
        return
    raise DbtInteropArgumentError(
        "--defer-clone-from cannot be used with --defer-to",
        code="C239",
    )


def _validate_event_time_cursor_conflict(
    *, command: DbtInteropCommand, parsed: DbtInteropParsedArgs
) -> None:
    if parsed.event_time_start is None or not _map_event_time_to_sqlbuild(command):
        return
    if parsed.start_cursor_ts is None and parsed.end_cursor_ts is None:
        return
    raise DbtInteropArgumentError(
        "--event-time-start/end conflict with --start-cursor-ts/end-cursor-ts",
        code="C234",
        help="Use dbt event-time flags or SQLBuild timestamp cursor overrides, not both.",
    )


def _validate_sqlbuild_flags_allowed(
    *, command: DbtInteropCommand, parsed: DbtInteropParsedArgs
) -> None:
    allowed: frozenset[str] = _allowed_sqlbuild_flags(command)
    for flag, present in (
        ("--start-cursor-ts", parsed.start_cursor_ts is not None),
        ("--end-cursor-ts", parsed.end_cursor_ts is not None),
        ("--start-cursor-int", parsed.start_cursor_int is not None),
        ("--end-cursor-int", parsed.end_cursor_int is not None),
        ("--defer-to", parsed.defer_to is not None),
        ("--defer-clone-from", parsed.defer_clone_from),
        ("--fail-fast", parsed.fail_fast),
        ("--force", parsed.force),
        ("--hard-copy", parsed.hard_copy),
    ):
        if present and flag not in allowed:
            raise DbtInteropArgumentError(
                f"{flag} is not a valid SQLBuild option for sqb dbt {command.value}",
                code="C232",
            )


def _allowed_sqlbuild_flags(command: DbtInteropCommand) -> frozenset[str]:
    cursor_flags: tuple[str, ...] = (
        "--start-cursor-ts",
        "--end-cursor-ts",
        "--start-cursor-int",
        "--end-cursor-int",
    )
    common_execution_flags: tuple[str, ...] = (
        *cursor_flags,
        "--defer-to",
        "--defer-clone-from",
        "--fail-fast",
        "--force",
        "--verbose",
    )
    if command in {DbtInteropCommand.RUN, DbtInteropCommand.BUILD}:
        return frozenset(common_execution_flags)
    if command == DbtInteropCommand.PLAN:
        return frozenset((*cursor_flags, "--defer-to", "--force"))
    if command == DbtInteropCommand.TEST:
        return frozenset()
    return frozenset()


def _map_full_refresh_to_sqlbuild(command: DbtInteropCommand) -> bool:
    return command in {DbtInteropCommand.PLAN, DbtInteropCommand.RUN, DbtInteropCommand.BUILD}


def _map_event_time_to_sqlbuild(command: DbtInteropCommand) -> bool:
    return command in {DbtInteropCommand.PLAN, DbtInteropCommand.RUN, DbtInteropCommand.BUILD}
