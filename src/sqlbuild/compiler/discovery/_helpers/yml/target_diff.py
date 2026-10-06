"""Loading and validation for per-target diff limits."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from sqlbuild.compiler.discovery._helpers.validation.supported_keys import (
    reject_unknown_mapping_keys,
)
from sqlbuild.compiler.discovery.exceptions import ProjectConfigError
from sqlbuild.spec.contracts.constants import UNLIMITED_DIFF_FULL_ROWS
from sqlbuild.spec.contracts.models import TargetDiffConfig

_MAX_FULL_ROWS_KEY: str = "max_full_rows"


def load_target_diff(*, payload: object, target_name: str, file_path: Path) -> TargetDiffConfig:
    """Parse one target's optional `[targets.<name>.diff]` section."""

    label: str = f"targets.{target_name}.diff"
    if payload is None:
        return TargetDiffConfig()
    if not isinstance(payload, dict):
        raise ProjectConfigError(f"{file_path} {label} must be a mapping")
    mapping: dict[str, object] = cast(dict[str, object], payload)
    reject_unknown_mapping_keys(
        mapping=mapping,
        allowed=frozenset({_MAX_FULL_ROWS_KEY}),
        file_path=file_path,
        label=label,
        error_class=ProjectConfigError,
    )
    value: object | None = mapping.get(_MAX_FULL_ROWS_KEY)
    if value is None:
        return TargetDiffConfig()
    if value == UNLIMITED_DIFF_FULL_ROWS:
        return TargetDiffConfig(max_full_rows="unlimited")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ProjectConfigError(
            f"{file_path} {label}.{_MAX_FULL_ROWS_KEY} must be an integer >= 1 or "
            f"'{UNLIMITED_DIFF_FULL_ROWS}'"
        )
    return TargetDiffConfig(max_full_rows=value)
