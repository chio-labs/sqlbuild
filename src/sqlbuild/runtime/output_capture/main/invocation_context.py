"""Load bounded opaque invocation context for subprocess integrations."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import cast

from sqlbuild.runtime.output_capture._helpers.json import freeze_command_output_json
from sqlbuild.runtime.output_capture.constants import (
    INVOCATION_CONTEXT_ENV,
    MAX_INVOCATION_CONTEXT_BYTES,
    MAX_INVOCATION_CONTEXT_DEPTH,
)
from sqlbuild.runtime.output_capture.exceptions import OutputCaptureInputError


def invocation_context_from_environment(
    *, environment: Mapping[str, str] | None = None
) -> Mapping[str, object]:
    """Return validated opaque invocation metadata supplied by an integration."""

    raw: str | None = (os.environ if environment is None else environment).get(
        INVOCATION_CONTEXT_ENV
    )
    if raw is None:
        return {}
    if len(raw.encode("utf-8")) > MAX_INVOCATION_CONTEXT_BYTES:
        raise OutputCaptureInputError(
            f"{INVOCATION_CONTEXT_ENV} must not exceed {MAX_INVOCATION_CONTEXT_BYTES} bytes"
        )
    try:
        loaded: object = json.loads(raw)
    except json.JSONDecodeError as error:
        raise OutputCaptureInputError(
            f"{INVOCATION_CONTEXT_ENV} must contain valid JSON"
        ) from error
    if not isinstance(loaded, dict):
        raise OutputCaptureInputError(f"{INVOCATION_CONTEXT_ENV} must contain a JSON object")
    _validate_depth(value=loaded, depth=1)
    try:
        frozen: object = freeze_command_output_json(value=loaded, path="external_context")
    except ValueError as error:
        raise OutputCaptureInputError(str(error)) from error
    if not isinstance(frozen, Mapping):
        raise OutputCaptureInputError(f"{INVOCATION_CONTEXT_ENV} must contain a JSON object")
    return cast(Mapping[str, object], frozen)


def _validate_depth(*, value: object, depth: int) -> None:
    if depth > MAX_INVOCATION_CONTEXT_DEPTH:
        raise OutputCaptureInputError(
            f"{INVOCATION_CONTEXT_ENV} must not exceed {MAX_INVOCATION_CONTEXT_DEPTH} levels"
        )
    if isinstance(value, dict):
        for item in value.values():
            _validate_depth(value=item, depth=depth + 1)
    elif isinstance(value, list):
        for item in value:
            _validate_depth(value=item, depth=depth + 1)
