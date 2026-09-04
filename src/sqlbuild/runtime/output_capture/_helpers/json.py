"""Command-output JSON compatibility helpers."""

from __future__ import annotations

import math
from collections.abc import Mapping
from types import MappingProxyType

from sqlbuild.runtime.output_capture.exceptions import CommandOutputValidationError


def freeze_command_output_json(*, value: object, path: str) -> object:
    """Validate and recursively freeze a JSON-compatible value."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CommandOutputValidationError(f"{path} must not contain NaN or infinity")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CommandOutputValidationError(f"{path} keys must be strings")
            frozen[key] = freeze_command_output_json(value=item, path=f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(
            freeze_command_output_json(value=item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    raise CommandOutputValidationError(
        f"{path} contains non-JSON value of type {type(value).__name__}"
    )
