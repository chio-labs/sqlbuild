"""Constants for the native SQL-test planning glue."""

from __future__ import annotations

CURSOR_INTRINSIC_NAMES: tuple[str, ...] = ("__cursor_start", "__cursor_end")
SQL_TEST_INPUT_FAILURE: str = "input"
SQL_TEST_DECIMAL_OVERFLOW: str = "decimal_overflow"
SQL_TEST_EXTENSION_CALLBACK: str = "extension_callback"
