"""Public execution JSON writing entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.output._helpers.execution_protocol_v1 import (
    write_execution_json_output as _write_execution_json_output,
)


def write_execution_json_output(
    *, payload: str, json_output: bool, json_output_path: Path | None
) -> None:
    """Write execution JSON to stdout or a requested side-channel file."""

    _write_execution_json_output(
        payload=payload, json_output=json_output, json_output_path=json_output_path
    )
