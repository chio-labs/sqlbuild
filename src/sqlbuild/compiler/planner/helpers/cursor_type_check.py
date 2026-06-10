"""Warehouse cursor column type consistency checking."""

from __future__ import annotations

import logging
from typing import Any

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.planner.models import PlanWarning
from sqlbuild.compiler.planner.types import CursorType, WarningSeverity
from sqlbuild.shared.helpers.diagnostics_logging import log_debug_event
from sqlbuild.shared.helpers.polyglot import import_polyglot

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.planner")
_TIMESTAMP_SUBSTRINGS: frozenset[str] = frozenset(
    {
        "TIMESTAMP",
        "DATETIME",
        "DATE",
    }
)

_INTEGER_SUBSTRINGS: frozenset[str] = frozenset(
    {
        "BIGINT",
        "SMALLINT",
        "TINYINT",
        "MEDIUMINT",
        "INT",
    }
)

_POLYGLOT_TIMESTAMP_TYPE_NAMES: frozenset[str] = frozenset(
    {
        "TIMESTAMP",
        "TIMESTAMPNTZ",
        "TIMESTAMPLTZ",
        "TIMESTAMPTZ",
        "TIMESTAMP_S",
        "TIMESTAMP_MS",
        "TIMESTAMP_NS",
        "DATE",
        "DATE32",
        "DATETIME",
        "DATETIME2",
        "DATETIME64",
        "SMALLDATETIME",
    }
)

_POLYGLOT_INTEGER_TYPE_NAMES: frozenset[str] = frozenset(
    {
        "INT",
        "BIG_INT",
        "BIGINT",
        "SMALL_INT",
        "SMALLINT",
        "TINY_INT",
        "TINYINT",
        "MEDIUMINT",
        "INT128",
        "INT256",
        "UINT",
        "UBIGINT",
        "USMALLINT",
        "UTINYINT",
        "UMEDIUMINT",
        "UINT128",
        "UINT256",
    }
)


def check_cursor_type_consistency(
    *,
    model_name: str,
    cursor_column: str | None,
    cursor_type: str | None,
    warehouse_columns: tuple[ColumnInfo, ...],
    sql_analysis_enabled: bool,
) -> PlanWarning | None:
    """Check whether the warehouse column type is consistent with cursor_type.

    Returns a warning or error if a mismatch is detected, None otherwise.
    With sql_analysis enabled, uses parsed type classification for a hard error on
    clear mismatches. Without sql_analysis, uses heuristic substring matching for a
    softer warning.
    """

    if cursor_column is None or cursor_type is None:
        return None

    warehouse_type: str | None = _find_column_type(
        columns=warehouse_columns, column_name=cursor_column
    )
    if warehouse_type is None:
        return None

    declared: CursorType | None = _parse_cursor_type(cursor_type)
    if declared is None:
        return None

    if sql_analysis_enabled:
        return _check_with_polyglot(
            model_name=model_name,
            cursor_column=cursor_column,
            declared=declared,
            warehouse_type=warehouse_type,
        )

    return _check_with_heuristic(
        model_name=model_name,
        cursor_column=cursor_column,
        declared=declared,
        warehouse_type=warehouse_type,
    )


def _find_column_type(
    *,
    columns: tuple[ColumnInfo, ...],
    column_name: str,
) -> str | None:
    """Find the warehouse type string for a column by name (case-insensitive)."""

    col: ColumnInfo
    for col in columns:
        if col.name.upper() == column_name.upper():
            return col.type
    return None


def _parse_cursor_type(cursor_type: str) -> CursorType | None:
    """Parse a cursor_type config string to the enum, or None if unrecognized."""

    try:
        return CursorType(cursor_type)
    except ValueError:
        return None


def _check_with_polyglot(
    *,
    model_name: str,
    cursor_column: str,
    declared: CursorType,
    warehouse_type: str,
) -> PlanWarning | None:
    """Classify warehouse type via sql_analysis and return error on clear mismatch."""

    detected: CursorType | None = _classify_type_with_polyglot(warehouse_type)
    if detected is None:
        return None

    if detected != declared:
        return PlanWarning(
            model_name=model_name,
            severity=WarningSeverity.ERROR,
            message=(
                f"cursor column '{cursor_column}' has warehouse type '{warehouse_type}' "
                f"which is {detected.value}, but cursor_type is '{declared.value}'"
            ),
        )

    return None


def _check_with_heuristic(
    *,
    model_name: str,
    cursor_column: str,
    declared: CursorType,
    warehouse_type: str,
) -> PlanWarning | None:
    """Classify warehouse type via substring heuristic and warn on mismatch."""

    detected: CursorType | None = _classify_type_heuristic(warehouse_type)
    if detected is None:
        return None

    if detected != declared:
        return PlanWarning(
            model_name=model_name,
            severity=WarningSeverity.WARNING,
            message=(
                f"cursor column '{cursor_column}' has warehouse type '{warehouse_type}' "
                f"which appears to be {detected.value}, but cursor_type is '{declared.value}'"
            ),
        )

    return None


def _classify_type_heuristic(warehouse_type: str) -> CursorType | None:
    """Classify a warehouse type string as timestamp or integer via substrings.

    Returns the matching CursorType or None if unclassifiable. Checks timestamp
    substrings first to avoid 'INT' matching inside compound names like
    'TIMESTAMP_NTZ'.
    """

    upper: str = warehouse_type.upper()

    substring: str
    for substring in _TIMESTAMP_SUBSTRINGS:
        if substring in upper:
            return CursorType.TIMESTAMP

    for substring in _INTEGER_SUBSTRINGS:
        if substring in upper:
            return CursorType.INTEGER

    return None


def _classify_type_with_polyglot(warehouse_type: str) -> CursorType | None:
    """Classify a warehouse type string using sql_analysis type parsing.

    Returns the matching CursorType or None if sql_analysis is unavailable or the
    type cannot be classified.
    """

    polyglot_module: Any | None = import_polyglot()
    if polyglot_module is None:
        return None

    try:
        parsed: Any = polyglot_module.parse_data_type(warehouse_type, dialect="generic")
    except Exception as error:
        log_debug_event(
            _DEBUG_LOGGER,
            "cursor type classification parse failed; falling back",
            sqlbuild_warehouse_type=warehouse_type,
            sqlbuild_error=str(error),
        )
        return None

    args: dict[str, Any] = dict(getattr(parsed, "args", {}) or {})
    type_name: str = str(args.get("data_type", "")).upper()
    if type_name == "CUSTOM":
        type_name = str(args.get("name", "")).upper().replace("_", "")

    if type_name in _POLYGLOT_TIMESTAMP_TYPE_NAMES:
        return CursorType.TIMESTAMP
    if type_name in _POLYGLOT_INTEGER_TYPE_NAMES:
        return CursorType.INTEGER

    return None
