"""Remove run-specific noise that legitimately differs between two identical compiles."""

from __future__ import annotations

from scripts.compiler_differential._helpers.comparing.compare import as_json_object
from scripts.compiler_differential.constants import (
    ELAPSED_TIME_MASK,
    ELAPSED_TIME_PATTERN,
    MANIFEST_VOLATILE_METADATA,
    STRIPPED_REPORT_FIELDS,
)
from sqlbuild.compiler.frontier.classes.stage_capture_encoder import mask_capture_noise


def normalize_artifact_text(text: str) -> str:
    """Mask invocation ids and engine store suffixes, which differ by design."""

    return mask_capture_noise(text)


def normalize_stderr(text: str) -> str:
    """Mask elapsed times as well as the artifact noise in progress and diagnostic output."""

    return ELAPSED_TIME_PATTERN.sub(ELAPSED_TIME_MASK, normalize_artifact_text(text))


def strip_report_fields(payload: object) -> object:
    """Drop the timings and engine fields of a top-level command report."""

    report: dict[str, object] | None = as_json_object(payload)
    if report is None:
        return payload
    return {key: value for key, value in report.items() if key not in STRIPPED_REPORT_FIELDS}


def strip_manifest_metadata(payload: object) -> object:
    """Drop the manifest generation time and invocation id."""

    manifest: dict[str, object] | None = as_json_object(payload)
    metadata: dict[str, object] | None = (
        None if manifest is None else as_json_object(manifest.get("metadata"))
    )
    if manifest is None or metadata is None:
        return payload
    return {
        **manifest,
        "metadata": {
            key: value for key, value in metadata.items() if key not in MANIFEST_VOLATILE_METADATA
        },
    }
