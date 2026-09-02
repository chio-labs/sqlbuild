"""dbt JSON event parsing and streaming helpers."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO, cast

from sqlbuild.integrations.dbt.exceptions import DbtInteropRuntimeError
from sqlbuild.integrations.dbt.models import DbtNodeExecutionResult, DbtNodeMessage
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.presentation.main.aligned_name_value import format_aligned_name_value
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle

_DBT_ERROR_LEVEL: str = "error"
_DBT_NODE_FINISHED_EVENT: str = "NodeFinished"
_DBT_NODE_MESSAGE_EVENT_NAMES: frozenset[str] = frozenset(
    {"RunResultError", "RunResultFailure", "RunResultWarning", "GenericExceptionOnRun"}
)
_DBT_NODE_MESSAGE_LEVELS: frozenset[str] = frozenset({"warn", "error"})
_DBT_NODE_STARTED_EVENT_NAMES: frozenset[str] = frozenset({"LogStartLine", "NodeStarted"})
_DBT_OUTCOME_STATUSES: frozenset[str] = frozenset(
    {
        "error",
        "fail",
        "failed",
        "ok",
        "pass",
        "passed",
        "skip",
        "skipped",
        "success",
        "warn",
        "warning",
    }
)
_DBT_RESULT_EVENT_NAMES: frozenset[str] = frozenset(
    {
        "LogModelResult",
        "LogSeedResult",
        "LogSnapshotResult",
        "LogTestResult",
        "LogBatchResult",
        "LogFunctionResult",
        "NodeFinished",
    }
)
_DBT_START_STATUSES: frozenset[str] = frozenset({"start"})
_DBT_STATUS_ERROR_VALUES: frozenset[str] = frozenset({"error", "fail", "failed"})
_DBT_STATUS_OK_VALUES: frozenset[str] = frozenset({"ok", "success"})
_DBT_STATUS_PASS_VALUES: frozenset[str] = frozenset({"pass", "passed"})
_DBT_STATUS_SKIP_VALUES: frozenset[str] = frozenset({"skip", "skipped"})
_DBT_STATUS_WARN_VALUES: frozenset[str] = frozenset({"warn", "warning"})
_DBT_WARN_LEVEL: str = "warn"
_DBT_DURATION_WIDTH: int = 7
_DBT_STATUS_REFRESH_SECONDS: float = 1.0


@dataclass
class _DbtStreamState:
    pending_messages: dict[str, list[DbtNodeMessage]] = field(default_factory=dict)
    results: list[DbtNodeExecutionResult] = field(default_factory=list)
    recorded_unique_ids: set[str] = field(default_factory=set)
    started_indexes: dict[str, int] = field(default_factory=dict)
    active_nodes: dict[str, tuple[str, float]] = field(default_factory=dict)
    display_index: int = 0
    use_color: bool = False


def execute_dbt_json_event_stream(
    *,
    argv: tuple[str, ...],
    cwd: Path | None,
    stream: TextIO,
    use_color: bool,
    target_path: Path | None,
    display_total: int | None = None,
    on_node_result: Callable[[DbtNodeExecutionResult], None] | None = None,
    detail_by_unique_id: dict[str, str] | None = None,
    enable_status: bool = True,
) -> tuple[int, tuple[DbtNodeExecutionResult, ...]]:
    """Run dbt and render SQLBuild-styled rows from JSON events."""

    with OperationLifecycle(
        operation_kind="subprocess",
        operation_name="dbt_command",
        auto_fail_base_exceptions=False,
    ) as lifecycle:
        returncode, results, process_id = _execute_dbt_json_event_stream(
            argv=argv,
            cwd=cwd,
            stream=stream,
            use_color=use_color,
            target_path=target_path,
            display_total=display_total,
            on_node_result=on_node_result,
            detail_by_unique_id=detail_by_unique_id,
            enable_status=enable_status,
        )
        if returncode == 0:
            lifecycle.completed(exit_code=0, process_id=process_id)
        else:
            lifecycle.failed(
                error_code=f"exit_{returncode}",
                exit_code=returncode,
                process_id=process_id,
                signal_number=-returncode if returncode < 0 else None,
            )
        return returncode, results


def _execute_dbt_json_event_stream(
    *,
    argv: tuple[str, ...],
    cwd: Path | None,
    stream: TextIO,
    use_color: bool,
    target_path: Path | None,
    display_total: int | None,
    on_node_result: Callable[[DbtNodeExecutionResult], None] | None,
    detail_by_unique_id: dict[str, str] | None,
    enable_status: bool,
) -> tuple[int, tuple[DbtNodeExecutionResult, ...], int | None]:
    style: CliStyle = CliStyle(use_color=use_color)
    state: _DbtStreamState = _DbtStreamState(use_color=use_color)
    status_box: dict[str, TransientStatusReporter | None] = {"status": None}
    status_lock: threading.Lock = threading.Lock()
    status_stop: threading.Event = threading.Event()
    status_thread: threading.Thread | None = None
    process: subprocess.Popen[str] | None = None
    process_waited = False
    try:
        process = _launch_dbt_process(
            argv=argv,
            cwd=cwd,
            target_path=target_path,
        )
        status_box["status"] = (
            _start_dbt_status(stream=stream, use_color=use_color) if enable_status else None
        )
        status_thread = _start_active_node_status_refresher(
            stream=stream,
            use_color=use_color,
            enabled=enable_status,
            active_nodes=state.active_nodes,
            status_box=status_box,
            status_lock=status_lock,
            status_stop=status_stop,
        )
        if process.stdout is not None:
            try:
                for line in process.stdout:
                    state.display_index, status_box = _handle_dbt_output_line(
                        line=line,
                        stream=stream,
                        style=style,
                        display_total=display_total,
                        detail_by_unique_id=detail_by_unique_id,
                        enable_status=enable_status,
                        state=state,
                        status_box=status_box,
                        status_lock=status_lock,
                        on_node_result=on_node_result,
                    )
            finally:
                try:
                    process.stdout.close()
                except BaseException:
                    pass
        returncode: int = process.wait()
        process_waited = True
        process_id: object = getattr(process, "pid", None)
        return (
            returncode,
            tuple(state.results),
            process_id
            if isinstance(process_id, int) and not isinstance(process_id, bool) and process_id >= 0
            else None,
        )
    finally:
        _cleanup_dbt_runtime(
            process=process,
            process_waited=process_waited,
            status_stop=status_stop,
            status_thread=status_thread,
            status_box=status_box,
            status_lock=status_lock,
        )


def _handle_dbt_output_line(
    *,
    line: str,
    stream: TextIO,
    style: CliStyle,
    display_total: int | None,
    detail_by_unique_id: dict[str, str] | None,
    enable_status: bool,
    state: _DbtStreamState,
    status_box: dict[str, TransientStatusReporter | None],
    status_lock: threading.Lock,
    on_node_result: Callable[[DbtNodeExecutionResult], None] | None,
) -> tuple[int, dict[str, TransientStatusReporter | None]]:
    event: dict[str, object] | None = parse_dbt_json_event(line=line)
    if event is None:
        return state.display_index, status_box
    message: DbtNodeMessage | None = parse_dbt_node_message(event=event)
    if message is not None:
        unique_id: str | None = _event_unique_id(event)
        if unique_id is not None:
            state.pending_messages.setdefault(unique_id, []).append(message)
        return state.display_index, status_box
    node_start_message: str | None = parse_dbt_node_start_message(event=event)
    if node_start_message is not None:
        if enable_status:
            with status_lock:
                status_box["status"] = _update_message_status(
                    status=status_box["status"],
                    message=node_start_message,
                    stream=stream,
                    use_color=state.use_color,
                )
        start_result: DbtNodeExecutionResult | None = parse_dbt_node_start_result(event=event)
        if start_result is not None and start_result.unique_id not in state.started_indexes:
            state.display_index += 1
            state.started_indexes[start_result.unique_id] = state.display_index
            status_box = _close_status(status_box=status_box, status_lock=status_lock)
            render_dbt_node_result(
                stream=stream,
                style=style,
                result=start_result,
                display_index=state.display_index,
                display_total=display_total,
                detail=_node_detail(
                    unique_id=start_result.unique_id,
                    detail_by_unique_id=detail_by_unique_id,
                ),
            )
            if enable_status:
                with status_lock:
                    state.active_nodes[start_result.unique_id] = (
                        start_result.node_name,
                        time.monotonic(),
                    )
                    status_box["status"] = _update_active_node_status(
                        status=status_box["status"],
                        active_nodes=state.active_nodes,
                        stream=stream,
                        use_color=state.use_color,
                    )
        return state.display_index, status_box
    result: DbtNodeExecutionResult | None = parse_dbt_node_result(
        event=event,
        messages_by_unique_id=state.pending_messages,
    )
    if result is None or result.unique_id in state.recorded_unique_ids:
        return state.display_index, status_box
    state.recorded_unique_ids.add(result.unique_id)
    status_box = _close_status(status_box=status_box, status_lock=status_lock)
    with status_lock:
        state.active_nodes.pop(result.unique_id, None)
    state.results.append(result)
    if on_node_result is not None:
        on_node_result(result)
    result_display_index: int | None = state.started_indexes.get(result.unique_id)
    if result_display_index is None:
        state.display_index += 1
        result_display_index = state.display_index
    render_dbt_node_result(
        stream=stream,
        style=style,
        result=result,
        display_index=result_display_index,
        display_total=display_total,
        detail=_node_detail(
            unique_id=result.unique_id,
            detail_by_unique_id=detail_by_unique_id,
        ),
    )
    if enable_status:
        with status_lock:
            status_box["status"] = _update_active_node_status(
                status=status_box["status"],
                active_nodes=state.active_nodes,
                stream=stream,
                use_color=state.use_color,
            )
    return state.display_index, status_box


def _cleanup_dbt_runtime(
    *,
    process: subprocess.Popen[str] | None,
    process_waited: bool,
    status_stop: threading.Event,
    status_thread: threading.Thread | None,
    status_box: dict[str, TransientStatusReporter | None],
    status_lock: threading.Lock,
) -> None:
    try:
        status_stop.set()
    except BaseException:
        pass
    if status_thread is not None:
        try:
            status_thread.join(timeout=1)
        except BaseException:
            pass
    try:
        _ = _close_status(status_box=status_box, status_lock=status_lock)
    except BaseException:
        pass
    if process is not None and not process_waited:
        _stop_dbt_process(process=process)


def _stop_dbt_process(*, process: subprocess.Popen[str]) -> None:
    returncode: int | None = None
    try:
        returncode = process.poll()
    except BaseException:
        pass
    if returncode is None:
        try:
            process.terminate()
        except BaseException:
            pass
    try:
        _ = process.wait(timeout=1)
        return
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except BaseException:
            pass
    except BaseException:
        try:
            process.kill()
        except BaseException:
            pass
    try:
        _ = process.wait(timeout=1)
    except BaseException:
        pass


def _launch_dbt_process(
    *,
    argv: tuple[str, ...],
    cwd: Path | None,
    target_path: Path | None,
) -> subprocess.Popen[str]:
    try:
        return subprocess.Popen(
            argv,
            cwd=cwd,
            env=_build_dbt_json_env(target_path=target_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as error:
        raise DbtInteropRuntimeError(
            "failed to execute dbt",
            help=str(error),
        ) from error


def _start_dbt_status(*, stream: TextIO, use_color: bool) -> TransientStatusReporter | None:
    if not stream.isatty():
        return None
    status: TransientStatusReporter = TransientStatusReporter(
        stream=stream,
        use_color=use_color,
    )
    status.start("Waiting for dbt node output...")
    return status


def _start_active_node_status_refresher(
    *,
    stream: TextIO,
    use_color: bool,
    enabled: bool,
    active_nodes: dict[str, tuple[str, float]],
    status_box: dict[str, TransientStatusReporter | None],
    status_lock: threading.Lock,
    status_stop: threading.Event,
    refresh_seconds: float | None = None,
) -> threading.Thread | None:
    if not enabled or not stream.isatty():
        return None
    actual_refresh_seconds: float = (
        _DBT_STATUS_REFRESH_SECONDS if refresh_seconds is None else refresh_seconds
    )
    thread: threading.Thread = threading.Thread(
        target=_run_active_node_status_refresher,
        kwargs={
            "stream": stream,
            "use_color": use_color,
            "active_nodes": active_nodes,
            "status_box": status_box,
            "status_lock": status_lock,
            "status_stop": status_stop,
            "refresh_seconds": actual_refresh_seconds,
        },
        daemon=True,
    )
    thread.start()
    return thread


def _run_active_node_status_refresher(
    *,
    stream: TextIO,
    use_color: bool,
    active_nodes: dict[str, tuple[str, float]],
    status_box: dict[str, TransientStatusReporter | None],
    status_lock: threading.Lock,
    status_stop: threading.Event,
    refresh_seconds: float,
) -> dict[str, TransientStatusReporter | None]:
    while not status_stop.wait(refresh_seconds):
        with status_lock:
            status_box["status"] = _update_active_node_status(
                status=status_box["status"],
                active_nodes=active_nodes,
                stream=stream,
                use_color=use_color,
            )
    return status_box


def _update_message_status(
    *,
    status: TransientStatusReporter | None,
    message: str,
    stream: TextIO,
    use_color: bool,
) -> TransientStatusReporter | None:
    if status is None:
        status = TransientStatusReporter(stream=stream, use_color=use_color)
        status.start(message)
        return status
    status.update(message)
    return status


def _close_status(
    *,
    status_box: dict[str, TransientStatusReporter | None],
    status_lock: threading.Lock,
) -> dict[str, TransientStatusReporter | None]:
    with status_lock:
        if status_box["status"] is not None:
            status_box["status"].close()
            status_box["status"] = None
    return status_box


def _update_active_node_status(
    *,
    status: TransientStatusReporter | None,
    active_nodes: dict[str, tuple[str, float]],
    stream: TextIO,
    use_color: bool,
) -> TransientStatusReporter | None:
    if not stream.isatty() or not active_nodes:
        return None
    message: str = _format_active_node_status(active_nodes=active_nodes)
    if status is None:
        status = TransientStatusReporter(stream=stream, use_color=use_color)
        status.start(message)
        return status
    status.update(message)
    return status


def _format_active_node_status(*, active_nodes: dict[str, tuple[str, float]]) -> str:
    now: float = time.monotonic()
    ordered: tuple[tuple[str, float], ...] = tuple(
        sorted(active_nodes.values(), key=lambda item: item[1])
    )
    displayed: tuple[str, ...] = tuple(
        f"{name} {_format_elapsed_seconds(now=now, started_at=started_at)}"
        for name, started_at in ordered[:3]
    )
    extra_count: int = len(ordered) - len(displayed)
    suffix: str = f", +{extra_count} more" if extra_count > 0 else ""
    node_label: str = "node" if len(active_nodes) == 1 else "nodes"
    return f"running {len(active_nodes)} dbt {node_label}: {', '.join(displayed)}{suffix}"


def _format_elapsed_seconds(*, now: float, started_at: float) -> str:
    elapsed: int = max(0, int(now - started_at))
    return "<1s" if elapsed == 0 else f"{elapsed}s"


def parse_dbt_node_start_message(*, event: dict[str, object]) -> str | None:
    """Parse a dbt node-start event into a user-facing progress message."""

    info: dict[str, object] = _dict_value(event.get("info"))
    event_name: str | None = _str_value(info.get("name"))
    if event_name not in _DBT_NODE_STARTED_EVENT_NAMES:
        return None
    data: dict[str, object] = _dict_value(event.get("data"))
    node_info: dict[str, object] = _dict_value(data.get("node_info"))
    unique_id: str | None = _str_value(node_info.get("unique_id"))
    if unique_id is None:
        return None
    resource_type: str = _str_value(node_info.get("resource_type")) or "node"
    node_name: str = _str_value(node_info.get("node_name")) or unique_id
    return f"Running dbt {resource_type} {node_name}..."


def parse_dbt_node_start_result(*, event: dict[str, object]) -> DbtNodeExecutionResult | None:
    """Parse a dbt node-start event into a renderable START row."""

    info: dict[str, object] = _dict_value(event.get("info"))
    event_name: str | None = _str_value(info.get("name"))
    if event_name not in _DBT_NODE_STARTED_EVENT_NAMES:
        return None
    data: dict[str, object] = _dict_value(event.get("data"))
    node_info: dict[str, object] = _dict_value(data.get("node_info"))
    unique_id: str | None = _str_value(node_info.get("unique_id"))
    if unique_id is None:
        return None
    return DbtNodeExecutionResult(
        unique_id=unique_id,
        resource_type=_str_value(node_info.get("resource_type")) or "node",
        node_name=_str_value(node_info.get("node_name")) or unique_id,
        status="start",
        index=_int_value(data.get("index")),
        total=_int_value(data.get("total")) or _int_value(data.get("num_models")),
        execution_time=None,
        materialized=_str_value(node_info.get("materialized")),
    )


def parse_dbt_json_event(*, line: str) -> dict[str, object] | None:
    """Parse one dbt JSON log line, ignoring non-JSON output."""

    stripped: str = line.strip()
    if not stripped or not stripped.startswith("{"):
        return None
    try:
        payload: object = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def parse_dbt_node_message(*, event: dict[str, object]) -> DbtNodeMessage | None:
    """Parse a node-scoped warning/error message from a dbt event."""

    info: dict[str, object] = _dict_value(event.get("info"))
    data: dict[str, object] = _dict_value(event.get("data"))
    event_name: str | None = _str_value(info.get("name"))
    level: str | None = _str_value(info.get("level"))
    if event_name not in _DBT_NODE_MESSAGE_EVENT_NAMES and level not in _DBT_NODE_MESSAGE_LEVELS:
        return None
    if _event_unique_id(event) is None:
        return None
    message: str | None = _str_value(data.get("msg")) or _str_value(info.get("msg"))
    if not message:
        return None
    return DbtNodeMessage(level=level or "info", message=message.strip())


def parse_dbt_node_result(
    *,
    event: dict[str, object],
    messages_by_unique_id: dict[str, list[DbtNodeMessage]] | None = None,
) -> DbtNodeExecutionResult | None:
    """Parse a dbt node final result event."""

    info: dict[str, object] = _dict_value(event.get("info"))
    data: dict[str, object] = _dict_value(event.get("data"))
    event_name: str | None = _str_value(info.get("name"))
    if event_name not in _DBT_RESULT_EVENT_NAMES:
        return None
    node_info: dict[str, object] = _dict_value(data.get("node_info"))
    unique_id: str | None = _str_value(node_info.get("unique_id"))
    if unique_id is None:
        return None
    if event_name == _DBT_NODE_FINISHED_EVENT:
        run_result: dict[str, object] = _dict_value(data.get("run_result"))
        status: str | None = _str_value(run_result.get("status")) or _str_value(
            node_info.get("node_status")
        )
    else:
        status = _trusted_status(data.get("status")) or _str_value(node_info.get("node_status"))
    relation: dict[str, object] = _dict_value(node_info.get("node_relation"))
    messages: tuple[DbtNodeMessage, ...] = tuple((messages_by_unique_id or {}).pop(unique_id, []))
    return DbtNodeExecutionResult(
        unique_id=unique_id,
        resource_type=_str_value(node_info.get("resource_type")) or "node",
        node_name=_str_value(node_info.get("node_name")) or unique_id,
        status=status or "unknown",
        index=_int_value(data.get("index")),
        total=_int_value(data.get("total")) or _int_value(data.get("num_models")),
        execution_time=_float_value(data.get("execution_time")),
        materialized=_str_value(node_info.get("materialized")),
        relation_name=_str_value(relation.get("relation_name")),
        database=_str_value(relation.get("database")),
        schema=_str_value(relation.get("schema")),
        node_checksum=_str_value(node_info.get("node_checksum")),
        messages=messages,
    )


def _build_dbt_json_env(*, target_path: Path | None) -> dict[str, str]:
    env: dict[str, str] = {
        **os.environ.copy(),
        "DBT_LOG_FORMAT": "json",
        "PYTHONUNBUFFERED": "1",
    }
    if target_path is not None:
        env["DBT_TARGET_PATH"] = str(target_path)
        env["DBT_LOG_PATH"] = str(target_path)
    return env


def _event_unique_id(event: dict[str, object]) -> str | None:
    data: dict[str, object] = _dict_value(event.get("data"))
    node_info: dict[str, object] = _dict_value(data.get("node_info"))
    return _str_value(node_info.get("unique_id"))


def render_dbt_node_result(
    *,
    stream: TextIO,
    style: CliStyle,
    result: DbtNodeExecutionResult,
    display_index: int | None = None,
    display_total: int | None = None,
    detail: str = "",
) -> None:
    ctr: str = (
        f"{display_index}/{display_total}"
        if display_index is not None and display_total is not None
        else f"{result.index}/{result.total}"
        if result.index is not None and result.total is not None
        else str(display_index)
        if display_index is not None
        else "-"
    )
    resource_type: str = result.resource_type[:9]
    name: str = result.node_name[:30]
    status: str = _display_status(result.status)
    duration: str = f"{result.execution_time:.2f}s" if result.execution_time is not None else ""
    rendered_detail: str = style.muted(detail) if detail else ""
    value: str = (
        f"{_pad_styled(value=style.status(status=status), plain_value=status, width=6)} "
        f"{duration:<{_DBT_DURATION_WIDTH}}{rendered_detail}"
    ).rstrip()
    stream.write(
        f"  {ctr:<5} {resource_type:<9}"
        + format_aligned_name_value(
            plain_name=name,
            styled_name=style.dbt_object_name(name),
            value=value,
            name_column_width=30,
            prefix=" ",
        )
        + "\n"
    )
    for message in result.messages:
        message_status: str = (
            _DBT_WARN_LEVEL if message.level == _DBT_WARN_LEVEL else _DBT_ERROR_LEVEL
        )
        stream.write(f"         {style.status(status=message_status):<9} {message.message}\n")
    stream.flush()


def _node_detail(*, unique_id: str, detail_by_unique_id: dict[str, str] | None) -> str:
    if detail_by_unique_id is None:
        return ""
    return detail_by_unique_id.get(unique_id, "")


def _display_status(status: str) -> str:
    normalized: str = status.lower()
    if normalized in _DBT_STATUS_OK_VALUES:
        return "OK"
    if normalized in _DBT_STATUS_PASS_VALUES:
        return "PASS"
    if normalized in _DBT_STATUS_WARN_VALUES:
        return "WARN"
    if normalized in _DBT_STATUS_SKIP_VALUES:
        return "SKIP"
    if normalized in _DBT_STATUS_ERROR_VALUES:
        return "FAIL"
    if normalized in _DBT_START_STATUSES:
        return "START"
    return status.upper()


def _pad_styled(*, value: str, plain_value: str, width: int) -> str:
    return value + " " * max(0, width - len(plain_value))


def _trusted_status(value: object | None) -> str | None:
    status: str | None = _str_value(value)
    if status is None:
        return None
    return status if status.lower() in _DBT_OUTCOME_STATUSES else None


def _dict_value(value: object | None) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _str_value(value: object | None) -> str | None:
    return value if isinstance(value, str) and value else None


def _int_value(value: object | None) -> int | None:
    return value if isinstance(value, int) else None


def _float_value(value: object | None) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None
