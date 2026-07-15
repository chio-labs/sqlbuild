"""Configuration helpers for diff execution."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import cast

from sqlbuild.adapter.contract.models import RowDiffTolerance, RowDiffTolerances
from sqlbuild.executor.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.diff.constants import (
    ROW_DIFF_ABSOLUTE_TOLERANCE_KEY,
    ROW_DIFF_RELATIVE_TOLERANCE_KEY,
    ROW_DIFF_TOLERANCE_KEYS,
)


def parse_row_diff_tolerances(
    *,
    raw: object,
    label: str = "row_diff_tolerances",
) -> RowDiffTolerances:
    """Parse raw model config into typed row diff tolerances."""

    if raw is None:
        return RowDiffTolerances()
    if not isinstance(raw, dict):
        raise ExecutorInputError(f"{label} must be a mapping", code="X401")
    raw_mapping: dict[str, object] = cast(dict[str, object], raw)

    by_type: dict[str, RowDiffTolerance] = _parse_tolerance_section(
        raw=raw_mapping.get("by_type"),
        label=f"{label}.by_type",
        normalize_key=True,
    )
    by_column: dict[str, RowDiffTolerance] = _parse_tolerance_section(
        raw=raw_mapping.get("by_column"),
        label=f"{label}.by_column",
        normalize_key=False,
    )
    return RowDiffTolerances(by_type=by_type, by_column=by_column)


def _parse_tolerance_section(
    *,
    raw: object,
    label: str,
    normalize_key: bool,
) -> dict[str, RowDiffTolerance]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ExecutorInputError(f"{label} must be a mapping", code="X401")
    raw_mapping: dict[object, object] = cast(dict[object, object], raw)

    parsed: dict[str, RowDiffTolerance] = {}
    key: object
    rule: object
    for key, rule in raw_mapping.items():
        if not isinstance(key, str) or not key:
            raise ExecutorInputError(f"{label} keys must be non-empty strings", code="X402")
        parsed_key: str = key.lower() if normalize_key else key
        parsed[parsed_key] = _parse_tolerance_rule(raw=rule, label=f"{label}.{key}")
    return parsed


def _parse_tolerance_rule(*, raw: object, label: str) -> RowDiffTolerance:
    if not isinstance(raw, dict):
        raise ExecutorInputError(f"{label} must be a mapping", code="X401")
    raw_mapping: dict[str, object] = cast(dict[str, object], raw)

    unsupported_keys: tuple[str, ...] = tuple(
        str(key) for key in raw_mapping if key not in ROW_DIFF_TOLERANCE_KEYS
    )
    if unsupported_keys:
        unsupported: str = ", ".join(unsupported_keys)
        raise ExecutorInputError(f"{label} contains unsupported keys: {unsupported}", code="X403")

    absolute: Decimal | None = _parse_optional_decimal(
        raw=raw_mapping.get(ROW_DIFF_ABSOLUTE_TOLERANCE_KEY),
        label=f"{label}.absolute",
    )
    relative: Decimal | None = _parse_optional_decimal(
        raw=raw_mapping.get(ROW_DIFF_RELATIVE_TOLERANCE_KEY),
        label=f"{label}.relative",
    )
    if absolute is None and relative is None:
        raise ExecutorInputError(f"{label} must define absolute or relative", code="X404")
    return RowDiffTolerance(absolute=absolute, relative=relative)


def _parse_optional_decimal(*, raw: object, label: str) -> Decimal | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise ExecutorInputError(f"{label} must be numeric", code="X405")
    if not isinstance(raw, str | int | float | Decimal):
        raise ExecutorInputError(f"{label} must be numeric", code="X405")
    try:
        return Decimal(str(raw))
    except InvalidOperation as error:
        raise ExecutorInputError(f"{label} must be numeric", code="X405") from error
