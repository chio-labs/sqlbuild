"""Debug command output helpers."""

from __future__ import annotations

import json

from sqlbuild.cli.commands.main.helpers.debug.models import DebugLine, DebugResult
from sqlbuild.cli.commands.main.helpers.debug.types import DebugCheckStatus
from sqlbuild.shared.helpers.cli_style import CliStyle


def format_debug_text(result: DebugResult, *, use_color: bool) -> str:
    style: CliStyle = CliStyle(use_color=use_color)
    header: str = style.title("SQLBuild Diagnostics")
    lines: list[str] = ["", header, ""]
    _append_section(lines, "Runtime", result.runtime, style=style)
    _append_section(lines, "Configuration", result.configuration, style=style)
    _append_section(lines, "Connection", result.connection, style=style)
    return "\n".join(lines) + "\n"


def format_debug_json(result: DebugResult) -> str:
    return json.dumps(
        {
            "success": result.success,
            "runtime": [_line_to_json(line) for line in result.runtime],
            "configuration": [_line_to_json(line) for line in result.configuration],
            "connection": [_line_to_json(line) for line in result.connection],
        },
        sort_keys=True,
    )


def _append_section(
    lines: list[str], section_name: str, section_lines: tuple[DebugLine, ...], *, style: CliStyle
) -> None:
    rendered_section_name: str = style.section(f"{section_name}:")
    lines.append(rendered_section_name)
    line: DebugLine
    for line in section_lines:
        message: str = line.message
        if line.status is not None:
            status_message: str = line.status_message or line.message
            status: str = _format_status(line.status, status_message, style=style)
            message = status if not message else f"{message} {status}"
        lines.append(f"  {line.label}: {message}")
    lines.append("")


def _format_status(status: DebugCheckStatus, message: str, *, style: CliStyle) -> str:
    status_text: str = "OK" if status == DebugCheckStatus.OK else status.value
    rendered: str = f"[{status_text} {message}]"
    return style.status(status_text, rendered)


def _line_to_json(line: DebugLine) -> dict[str, str]:
    payload: dict[str, str] = {"label": line.label, "message": line.message}
    if line.status is not None:
        payload["status"] = line.status.value
    if line.status_message is not None:
        payload["status_message"] = line.status_message
    return payload
