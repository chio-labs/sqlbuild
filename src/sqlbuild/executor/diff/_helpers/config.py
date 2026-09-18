"""Configuration helpers for diff execution."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import cast

from sqlbuild.adapter.contract.models import RowDiffSampling, RowDiffTolerance, RowDiffTolerances
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.diff.constants import (
    ROW_DIFF_ABSOLUTE_TOLERANCE_KEY,
    ROW_DIFF_RELATIVE_TOLERANCE_KEY,
    ROW_DIFF_TOLERANCE_KEYS,
)
from sqlbuild.executor.diff.models import RowDiffSamplingOverride


def resolve_row_diff_sampling(
    *,
    raw_row_limit: object,
    raw_seed: object,
    override: RowDiffSamplingOverride,
    label: str,
) -> RowDiffSampling | None:
    """Resolve model sampling configuration with invocation overrides."""

    if override.exhaustive:
        return None
    row_limit: int | None = _parse_optional_non_negative_integer(
        raw=override.row_limit if override.row_limit is not None else raw_row_limit,
        label=f"{label}.row_diff_sample_rows",
    )
    if row_limit in (None, 0):
        return None
    seed: int | None = _parse_optional_integer(
        raw=override.seed if override.seed is not None else raw_seed,
        label=f"{label}.row_diff_sample_seed",
    )
    return RowDiffSampling(row_limit=row_limit, seed=seed or 0)


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


def parse_cli_tolerance_overrides(*, values: tuple[str, ...]) -> RowDiffTolerances:
    """Parse repeated COLUMN:KIND=VALUE CLI tolerance specifications."""

    raw_by_column: dict[str, dict[str, str]] = {}
    for value in values:
        column_and_kind, separator, amount = value.partition("=")
        column, kind_separator, kind = column_and_kind.partition(":")
        if (
            not separator
            or not kind_separator
            or not column
            or kind not in ROW_DIFF_TOLERANCE_KEYS
            or not amount
        ):
            raise ExecutorInputError(
                "diff --tolerance must use COLUMN:absolute=VALUE or COLUMN:relative=VALUE",
                code="X408",
            )
        raw_by_column.setdefault(column, {})[kind] = amount
    return parse_row_diff_tolerances(raw={"by_column": raw_by_column})


def merge_row_diff_tolerances(
    *, base: RowDiffTolerances, override: RowDiffTolerances | None
) -> RowDiffTolerances:
    """Overlay invocation tolerance rules on compiled model rules."""

    if override is None:
        return base
    return RowDiffTolerances(
        by_type={**base.by_type, **override.by_type},
        by_column={**base.by_column, **override.by_column},
        sampling=base.sampling,
    )


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


def _parse_optional_integer(*, raw: object, label: str) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ExecutorInputError(f"{label} must be an integer", code="X406")
    return raw


def _parse_optional_non_negative_integer(*, raw: object, label: str) -> int | None:
    value: int | None = _parse_optional_integer(raw=raw, label=label)
    if value is not None and value < 0:
        raise ExecutorInputError(f"{label} must be zero or greater", code="X407")
    return value
