"""Databricks adapter constants."""

NON_ROW_RESULT_COLUMN_NAMES: frozenset[str] = frozenset({"status", "result"})
TABLE_RELATION_METADATA_TYPES: frozenset[str] = frozenset({"managed", "external", "base table"})
DELTA_RELATION_FORMAT: str = "delta"
DELTA_DEFAULT_LOG_RETENTION_DAYS: int = 30
DELTA_DEFAULT_DELETED_FILE_RETENTION_DAYS: int = 7
DELTA_COLUMN_MAPPING_PROPERTY: str = "delta.columnMapping.mode"
DELTA_COLUMN_MAPPING_NAME_MODE: str = "name"
TABLE_OR_VIEW_NOT_FOUND_ERROR_CLASS: str = "TABLE_OR_VIEW_NOT_FOUND"
UNDEFINED_TABLE_SQLSTATE: str = "42P01"
