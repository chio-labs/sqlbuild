"""Constants for the native SQL-test planning glue."""

from __future__ import annotations

CURSOR_INTRINSIC_NAMES: tuple[str, ...] = ("__cursor_start", "__cursor_end")
SQL_TEST_ASSEMBLY_DEFERRAL_SITE: str = "sql_test_assembly"
