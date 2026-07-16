"""Databricks adapter constants."""

NON_ROW_RESULT_COLUMN_NAMES: frozenset[str] = frozenset({"status", "result"})
TABLE_RELATION_METADATA_TYPES: frozenset[str] = frozenset({"managed", "external", "base table"})
