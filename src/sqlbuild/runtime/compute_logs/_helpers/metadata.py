"""Compute log metadata JSON encoding and validation."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlbuild.runtime.compute_logs.constants import COMPLETED_AT_FIELD, COMPUTE_LOG_FORMAT_VERSION
from sqlbuild.runtime.compute_logs.exceptions import ComputeLogMetadataError
from sqlbuild.runtime.compute_logs.models import CaptureMetadata, FinalCaptureMetadata


def metadata_to_json(metadata: CaptureMetadata | FinalCaptureMetadata) -> str:
    """Serialize capture metadata deterministically without raw command arguments."""

    payload: dict[str, object] = {
        "format_version": metadata.format_version,
        "invocation_id": metadata.invocation_id,
        "command": metadata.command,
        "project_dir": metadata.project_dir,
        "started_at": _timestamp(metadata.started_at),
        "capture_date": metadata.capture_date,
        "target": metadata.target,
        "run_id": metadata.run_id,
    }
    if isinstance(metadata, FinalCaptureMetadata):
        payload.update(
            {
                "completed_at": _timestamp(metadata.completed_at),
                "exit_code": metadata.exit_code,
                "stdout_bytes": metadata.stdout_bytes,
                "stderr_bytes": metadata.stderr_bytes,
                "diagnostics_bytes": metadata.diagnostics_bytes,
            }
        )
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def metadata_from_json(raw_json: str) -> CaptureMetadata | FinalCaptureMetadata:
    """Decode and validate initial or final capture metadata."""

    try:
        payload: Any = json.loads(raw_json)
        if not isinstance(payload, dict):
            raise ComputeLogMetadataError("capture metadata must be a JSON object")
        common: dict[str, object] = {
            "format_version": payload["format_version"],
            "invocation_id": payload["invocation_id"],
            "command": payload["command"],
            "project_dir": payload["project_dir"],
            "started_at": datetime.fromisoformat(payload["started_at"].replace("Z", "+00:00")),
            "capture_date": payload["capture_date"],
            "target": payload.get("target"),
            "run_id": payload.get("run_id"),
        }
        if common["format_version"] != COMPUTE_LOG_FORMAT_VERSION:
            raise ComputeLogMetadataError("unsupported compute log format version")
        if COMPLETED_AT_FIELD not in payload:
            return CaptureMetadata(**common)  # type: ignore[arg-type]
        return FinalCaptureMetadata(
            **common,  # type: ignore[arg-type]
            completed_at=datetime.fromisoformat(payload["completed_at"].replace("Z", "+00:00")),
            exit_code=payload["exit_code"],
            stdout_bytes=payload["stdout_bytes"],
            stderr_bytes=payload["stderr_bytes"],
            diagnostics_bytes=payload["diagnostics_bytes"],
        )
    except ComputeLogMetadataError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ComputeLogMetadataError(f"invalid capture metadata: {error}") from error


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
