"""Configuration helpers for diff execution."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import cast

from sqlbuild.adapter.shared.models import RowDiffTolerance, RowDiffTolerances


def parse_row_diff_tolerances(
    raw: object,
    *,
    label: str = "row_diff_tolerances",
) -> RowDiffTolerances:
    """Parse raw model config into typed row diff tolerances."""

    if raw is None:
        return RowDiffTolerances()
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a mapping")
    raw_mapping: dict[str, object] = cast(dict[str, object], raw)

    by_type: dict[str, RowDiffTolerance] = _parse_tolerance_section(
        raw_mapping.get("by_type"),
        label=f"{label}.by_type",
        normalize_key=True,
    )
    by_column: dict[str, RowDiffTolerance] = _parse_tolerance_section(
        raw_mapping.get("by_column"),
        label=f"{label}.by_column",
        normalize_key=False,
    )
    return RowDiffTolerances(by_type=by_type, by_column=by_column)


def _parse_tolerance_section(
    raw: object,
    *,
    label: str,
    normalize_key: bool,
) -> dict[str, RowDiffTolerance]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a mapping")
    raw_mapping: dict[object, object] = cast(dict[object, object], raw)

    parsed: dict[str, RowDiffTolerance] = {}
    key: object
    rule: object
    for key, rule in raw_mapping.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{label} keys must be non-empty strings")
        parsed_key: str = key.lower() if normalize_key else key
        parsed[parsed_key] = _parse_tolerance_rule(rule, label=f"{label}.{key}")
    return parsed


def _parse_tolerance_rule(raw: object, *, label: str) -> RowDiffTolerance:
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a mapping")
    raw_mapping: dict[str, object] = cast(dict[str, object], raw)

    unsupported_keys: tuple[str, ...] = tuple(
        str(key) for key in raw_mapping if key not in {"absolute", "relative"}
    )
    if unsupported_keys:
        unsupported: str = ", ".join(unsupported_keys)
        raise ValueError(f"{label} contains unsupported keys: {unsupported}")

    absolute: Decimal | None = _parse_optional_decimal(
        raw_mapping.get("absolute"),
        label=f"{label}.absolute",
    )
    relative: Decimal | None = _parse_optional_decimal(
        raw_mapping.get("relative"),
        label=f"{label}.relative",
    )
    if absolute is None and relative is None:
        raise ValueError(f"{label} must define absolute or relative")
    return RowDiffTolerance(absolute=absolute, relative=relative)


def _parse_optional_decimal(raw: object, *, label: str) -> Decimal | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise ValueError(f"{label} must be numeric")
    if not isinstance(raw, str | int | float | Decimal):
        raise ValueError(f"{label} must be numeric")
    try:
        return Decimal(str(raw))
    except InvalidOperation as error:
        raise ValueError(f"{label} must be numeric") from error
