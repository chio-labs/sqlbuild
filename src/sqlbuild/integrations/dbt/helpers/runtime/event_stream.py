"""dbt JSON event parsing and streaming helpers."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import TextIO, cast

from sqlbuild.integrations.dbt.exceptions import DbtInteropRuntimeError
from sqlbuild.integrations.dbt.models import DbtNodeExecutionResult, DbtNodeMessage
from sqlbuild.shared.helpers.alignment import format_aligned_name_value
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.status import TransientStatusReporter

_RESULT_EVENT_NAMES: frozenset[str] = frozenset(
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

_NODE_MESSAGE_EVENT_NAMES: frozenset[str] = frozenset(
    {
        "RunResultError",
        "RunResultFailure",
        "RunResultWarning",
        "GenericExceptionOnRun",
    }
)

_NODE_STARTED_EVENT_NAMES: frozenset[str] = frozenset({"LogStartLine", "NodeStarted"})

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


def execute_dbt_json_event_stream(
    *,
    argv: tuple[str, ...],
    cwd: Path | None,
    stream: TextIO,
    use_color: bool,
    target_path: Path | None,
    display_total: int | None = None,
    on_node_result: Callable[[DbtNodeExecutionResult], None] | None = None,
) -> tuple[int, tuple[DbtNodeExecutionResult, ...]]:
    """Run dbt and render SQLBuild-styled rows from JSON events."""

    style: CliStyle = CliStyle(use_color=use_color)
    pending_messages: dict[str, list[DbtNodeMessage]] = {}
    results: list[DbtNodeExecutionResult] = []
    recorded_unique_ids: set[str] = set()
    display_index: int = 0
    status: TransientStatusReporter | None = _start_dbt_status(
        stream=stream,
        use_color=use_color,
    )
    try:
        process: subprocess.Popen[str] = subprocess.Popen(
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

    if process.stdout is not None:
        with process.stdout:
            for line in process.stdout:
                event: dict[str, object] | None = parse_dbt_json_event(line=line)
                if event is None:
                    continue
                message: DbtNodeMessage | None = parse_dbt_node_message(event=event)
                if message is not None:
                    unique_id: str | None = _event_unique_id(event)
                    if unique_id is not None:
                        pending_messages.setdefault(unique_id, []).append(message)
                    continue
                node_start_message: str | None = parse_dbt_node_start_message(event=event)
                if node_start_message is not None:
                    if status is None:
                        status = TransientStatusReporter(stream=stream, use_color=use_color)
                        status.start(node_start_message)
                    else:
                        status.update(node_start_message)
                    continue
                result: DbtNodeExecutionResult | None = parse_dbt_node_result(
                    event=event,
                    messages_by_unique_id=pending_messages,
                )
                if result is None:
                    continue
                if result.unique_id in recorded_unique_ids:
                    continue
                recorded_unique_ids.add(result.unique_id)
                if status is not None:
                    status.close()
                    status = None
                results.append(result)
                if on_node_result is not None:
                    on_node_result(result)
                display_index += 1
                render_dbt_node_result(
                    stream=stream,
                    style=style,
                    result=result,
                    display_index=display_index,
                    display_total=display_total,
                )

    returncode: int = process.wait()
    if status is not None:
        status.close()
    return returncode, tuple(results)


def _start_dbt_status(*, stream: TextIO, use_color: bool) -> TransientStatusReporter | None:
    if not stream.isatty():
        return None
    status: TransientStatusReporter = TransientStatusReporter(
        stream=stream,
        use_color=use_color,
    )
    status.start("Waiting for dbt node output...")
    return status


def parse_dbt_node_start_message(*, event: dict[str, object]) -> str | None:
    """Parse a dbt node-start event into a user-facing progress message."""

    info: dict[str, object] = _dict_value(event.get("info"))
    event_name: str | None = _str_value(info.get("name"))
    if event_name not in _NODE_STARTED_EVENT_NAMES:
        return None
    data: dict[str, object] = _dict_value(event.get("data"))
    node_info: dict[str, object] = _dict_value(data.get("node_info"))
    unique_id: str | None = _str_value(node_info.get("unique_id"))
    if unique_id is None or unique_id.startswith("unit_test"):
        return None
    resource_type: str = _str_value(node_info.get("resource_type")) or "node"
    node_name: str = _str_value(node_info.get("node_name")) or unique_id
    return f"Running dbt {resource_type} {node_name}..."


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
    if event_name not in _NODE_MESSAGE_EVENT_NAMES and level not in {"warn", "error"}:
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
    if event_name not in _RESULT_EVENT_NAMES:
        return None
    node_info: dict[str, object] = _dict_value(data.get("node_info"))
    unique_id: str | None = _str_value(node_info.get("unique_id"))
    if unique_id is None or unique_id.startswith("unit_test"):
        return None
    if event_name == "NodeFinished":
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
    stream.write(
        f"  {ctr:<5} {resource_type:<9}"
        + format_aligned_name_value(
            plain_name=name,
            styled_name=style.dbt_object_name(name),
            value=f"{style.status(status)} {duration}".rstrip(),
            name_column_width=30,
            prefix=" ",
        )
        + "\n"
    )
    for message in result.messages:
        message_status: str = "warn" if message.level == "warn" else "error"
        stream.write(f"         {style.status(message_status):<9} {message.message}\n")
    stream.flush()


def _display_status(status: str) -> str:
    normalized: str = status.lower()
    if normalized in {"ok", "success"}:
        return "OK"
    if normalized in {"pass", "passed"}:
        return "PASS"
    if normalized in {"warn", "warning"}:
        return "WARN"
    if normalized in {"skip", "skipped"}:
        return "SKIP"
    if normalized in {"error", "fail", "failed"}:
        return "FAIL"
    return status.upper()


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
