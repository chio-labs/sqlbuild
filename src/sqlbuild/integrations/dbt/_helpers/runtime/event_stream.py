"""dbt JSON event parsing and streaming helpers."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from sqlbuild._native import (
    DbtEventStream,
    DbtEventStreamUpdate,
    TransientStatusReporter,
    format_dbt_active_node_status,
)
from sqlbuild.integrations.dbt.exceptions import DbtInteropRuntimeError
from sqlbuild.integrations.dbt.models import DbtNodeExecutionResult
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle

_DBT_STATUS_REFRESH_SECONDS: float = 1.0


@dataclass
class _DbtStreamState:
    events: DbtEventStream
    results: list[DbtNodeExecutionResult] = field(default_factory=list)
    active_nodes: dict[str, tuple[str, float]] = field(default_factory=dict)
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
    state: _DbtStreamState = _DbtStreamState(
        events=DbtEventStream(
            display_total=display_total,
            detail_by_unique_id=detail_by_unique_id,
            use_color=use_color,
        ),
        use_color=use_color,
    )
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
                    state, status_box = _handle_dbt_output_line(
                        line=line,
                        stream=stream,
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
    enable_status: bool,
    state: _DbtStreamState,
    status_box: dict[str, TransientStatusReporter | None],
    status_lock: threading.Lock,
    on_node_result: Callable[[DbtNodeExecutionResult], None] | None,
) -> tuple[_DbtStreamState, dict[str, TransientStatusReporter | None]]:
    update: DbtEventStreamUpdate | None = state.events.consume(line)
    if update is None:
        return state, status_box
    if update.status_message is not None and enable_status:
        with status_lock:
            status_box["status"] = _update_message_status(
                status=status_box["status"],
                message=update.status_message,
                stream=stream,
                use_color=state.use_color,
            )
    result: DbtNodeExecutionResult | None = update.result
    if result is None or update.row is None:
        return state, status_box
    status_box = _close_status(status_box=status_box, status_lock=status_lock)
    if update.finished:
        with status_lock:
            state.active_nodes.pop(result.unique_id, None)
        state.results.append(result)
        if on_node_result is not None:
            on_node_result(result)
    stream.write(update.row)
    stream.flush()
    if enable_status:
        with status_lock:
            if not update.finished:
                state.active_nodes[result.unique_id] = (result.node_name, time.monotonic())
            status_box["status"] = _update_active_node_status(
                status=status_box["status"],
                active_nodes=state.active_nodes,
                stream=stream,
                use_color=state.use_color,
            )
    return state, status_box


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
    message: str = format_dbt_active_node_status(
        active_nodes=list(active_nodes.values()), now=time.monotonic()
    )
    if status is None:
        status = TransientStatusReporter(stream=stream, use_color=use_color)
        status.start(message)
        return status
    status.update(message)
    return status


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
