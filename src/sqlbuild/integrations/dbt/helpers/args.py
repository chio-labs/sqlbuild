"""Argument routing helpers for future `sqb dbt` commands."""

from __future__ import annotations

from collections.abc import Sequence

from sqlbuild.integrations.dbt.exceptions import DbtInteropArgumentError
from sqlbuild.integrations.dbt.models import DbtInteropRoutedArgs
from sqlbuild.integrations.dbt.types import DbtInteropCommand


def route_dbt_interop_args(
    *, command: DbtInteropCommand | str, args: Sequence[str]
) -> DbtInteropRoutedArgs:
    """Split raw `sqb dbt <command>` args into dbt and SQLBuild buckets."""

    try:
        normalized_command: DbtInteropCommand = DbtInteropCommand(command)
    except ValueError as exc:
        raise DbtInteropArgumentError(
            f"Unsupported sqb dbt command: {command}",
            code="C236",
        ) from exc
    state: _RouteState = _RouteState(command=normalized_command)
    index: int = 0
    while index < len(args):
        token: str = args[index]
        if token in {"--select", "-s"}:
            values: tuple[tuple[str, ...], int] = _consume_multi_value(args=args, index=index)
            _append_select(state=state, flag=token, values=values[0])
            index = values[1]
            continue
        if token == "--exclude":
            values = _consume_multi_value(args=args, index=index)
            _append_exclude(state=state, values=values[0])
            index = values[1]
            continue
        if token in _shared_value_flags():
            value, index = _consume_one_value(args=args, index=index)
            _append_shared_value(state=state, flag=token, value=value)
            continue
        if token in _shared_bool_flags():
            _append_shared_bool(state=state, flag=token)
            index += 1
            continue
        if token in _dbt_value_flags():
            value, index = _consume_one_value(args=args, index=index)
            state.dbt_args.extend((token, value))
            continue
        if token in _dbt_bool_flags():
            state.dbt_args.append(token)
            index += 1
            continue
        if token.startswith("--sqb-"):
            index = _route_sqlbuild_flag(state=state, args=args, index=index)
            continue
        state.dbt_args.append(token)
        index += 1

    _validate_event_time_pair(state)
    _validate_event_time_cursor_conflict(state)
    return DbtInteropRoutedArgs(
        command=state.command,
        select=tuple(state.select),
        exclude=tuple(state.exclude),
        dbt_args=tuple(state.dbt_args),
        sqlbuild_args=tuple(state.sqlbuild_args),
    )


class _RouteState:
    def __init__(self, *, command: DbtInteropCommand) -> None:
        self.command = command
        self.select: list[str] = []
        self.exclude: list[str] = []
        self.dbt_args: list[str] = []
        self.sqlbuild_args: list[str] = []
        self.event_time_start: str | None = None
        self.event_time_end: str | None = None
        self.event_time_mapped_to_sqlbuild: bool = False
        self.sqlbuild_start_cursor_ts: str | None = None
        self.sqlbuild_end_cursor_ts: str | None = None


def _append_select(*, state: _RouteState, flag: str, values: tuple[str, ...]) -> None:
    state.select.extend(values)
    state.dbt_args.extend((flag, *values))


def _append_exclude(*, state: _RouteState, values: tuple[str, ...]) -> None:
    state.exclude.extend(values)
    state.dbt_args.extend(("--exclude", *values))


def _append_shared_value(*, state: _RouteState, flag: str, value: str) -> None:
    state.dbt_args.extend((flag, value))
    if flag == "--vars":
        state.sqlbuild_args.extend(("--vars", value))
    elif flag == "--threads":
        state.sqlbuild_args.extend(("--concurrency", value))
    elif flag == "--event-time-start":
        state.event_time_start = value
        if _map_event_time_to_sqlbuild(state.command):
            state.event_time_mapped_to_sqlbuild = True
            state.sqlbuild_args.extend(("--start-cursor-ts", value))
    elif flag == "--event-time-end":
        state.event_time_end = value
        if _map_event_time_to_sqlbuild(state.command):
            state.event_time_mapped_to_sqlbuild = True
            state.sqlbuild_args.extend(("--end-cursor-ts", value))


def _append_shared_bool(*, state: _RouteState, flag: str) -> None:
    state.dbt_args.append(flag)
    if flag == "--full-refresh" and _map_full_refresh_to_sqlbuild(state.command):
        state.sqlbuild_args.append("--full-refresh")


def _route_sqlbuild_flag(*, state: _RouteState, args: Sequence[str], index: int) -> int:
    token: str = args[index]
    stripped_flag: str = f"--{token[len('--sqb-') :]}"
    if stripped_flag in _sqlbuild_denylist():
        raise DbtInteropArgumentError(
            f"{token} is not allowed for sqb dbt commands",
            code="C231",
            help="Use the canonical sqb dbt flag instead of a --sqb-* override.",
        )
    if stripped_flag not in _allowed_sqlbuild_flags(state.command):
        raise DbtInteropArgumentError(
            f"{token} is not a valid SQLBuild option for sqb dbt {state.command.value}",
            code="C232",
        )
    if stripped_flag in _sqlbuild_bool_flags():
        state.sqlbuild_args.append(stripped_flag)
        return index + 1
    value: str
    value, next_index = _consume_one_value(args=args, index=index)
    if stripped_flag == "--start-cursor-ts":
        state.sqlbuild_start_cursor_ts = value
    elif stripped_flag == "--end-cursor-ts":
        state.sqlbuild_end_cursor_ts = value
    state.sqlbuild_args.extend((stripped_flag, value))
    return next_index


def _validate_event_time_pair(state: _RouteState) -> None:
    if (state.event_time_start is None) == (state.event_time_end is None):
        return
    raise DbtInteropArgumentError(
        "--event-time-start and --event-time-end must be provided together",
        code="C233",
    )


def _validate_event_time_cursor_conflict(state: _RouteState) -> None:
    if not state.event_time_mapped_to_sqlbuild:
        return
    if state.sqlbuild_start_cursor_ts is None and state.sqlbuild_end_cursor_ts is None:
        return
    raise DbtInteropArgumentError(
        "--event-time-start/end conflict with --sqb-start-cursor-ts/end-cursor-ts",
        code="C234",
        help="Use dbt event-time flags or SQLBuild timestamp cursor overrides, not both.",
    )


def _consume_one_value(*, args: Sequence[str], index: int) -> tuple[str, int]:
    if index + 1 >= len(args) or args[index + 1].startswith("--"):
        raise DbtInteropArgumentError(
            f"{args[index]} requires a value",
            code="C235",
        )
    return args[index + 1], index + 2


def _consume_multi_value(*, args: Sequence[str], index: int) -> tuple[tuple[str, ...], int]:
    values: list[str] = []
    next_index: int = index + 1
    while next_index < len(args) and not args[next_index].startswith("--"):
        values.append(args[next_index])
        next_index += 1
    if not values:
        raise DbtInteropArgumentError(
            f"{args[index]} requires at least one value",
            code="C235",
        )
    return tuple(values), next_index


def _shared_value_flags() -> frozenset[str]:
    return frozenset(("--vars", "--threads", "--event-time-start", "--event-time-end"))


def _shared_bool_flags() -> frozenset[str]:
    return frozenset(("--full-refresh",))


def _dbt_value_flags() -> frozenset[str]:
    return frozenset(
        (
            "--project-dir",
            "--profiles-dir",
            "--profile",
            "--target",
            "--target-path",
            "--state",
            "--indirect-selection",
        )
    )


def _dbt_bool_flags() -> frozenset[str]:
    return frozenset(("--defer",))


def _sqlbuild_denylist() -> frozenset[str]:
    return frozenset(
        (
            "--select",
            "--exclude",
            "--project-dir",
            "--vars",
            "--full-refresh",
            "--concurrency",
            "--threads",
        )
    )


def _sqlbuild_bool_flags() -> frozenset[str]:
    return frozenset(("--hard-copy", "--fail-fast", "--verbose", "--force"))


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
