"""SQLite adapter constants."""

MINIMUM_SQLITE_VERSION: tuple[int, int, int] = (3, 44, 0)
DEFAULT_BUSY_TIMEOUT_SECONDS: float = 5.0
MEMORY_DATABASE_PATH: str = ":memory:"
MAIN_SCHEMA: str = "main"
SCHEMA_NAME_SEPARATOR: str = "__"
SCHEMA_REGISTRY_TABLE: str = "_sqlbuild_schemas"
RELATION_REGISTRY_TABLE: str = "_sqlbuild_relations"
INTERNAL_TABLE_NAMES: frozenset[str] = frozenset({SCHEMA_REGISTRY_TABLE, RELATION_REGISTRY_TABLE})
SQLITE_INTERNAL_PREFIX: str = "sqlite_"
CONNECTION_KEYS: frozenset[str] = frozenset({"path", "busy_timeout", "read_only"})
HASH_FUNCTION_NAME: str = "sqb_hash"
CURSOR_TEXT_FUNCTION_NAME: str = "sqb_cursor_text"
LOCKED_ERROR_FRAGMENTS: tuple[str, ...] = ("database is locked", "database table is locked")
MISSING_RELATION_ERROR_FRAGMENT: str = "no such table"
READ_STATEMENT_KEYWORDS: frozenset[str] = frozenset({"SELECT", "PRAGMA", "EXPLAIN", "VALUES"})
WRITE_GATE_POLL_SECONDS: float = 0.1
TYPEOF_TYPE_NAMES: dict[str, str] = {
    "integer": "INTEGER",
    "real": "REAL",
    "text": "TEXT",
    "blob": "BLOB",
}
UNTYPED_COLUMN_TYPE: str = "ANY"
DECIMAL_TEXT_TYPE_PREFIX: str = "TEXT "
DECIMAL_TYPE_NAMES: tuple[str, ...] = ("DECIMAL", "NUMERIC")
EXACT_DECIMAL_TYPE_PATTERN: str = r"^\s*(?:DECIMAL|NUMERIC)\s*\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\)\s*$"
NUMBER_DECIMAL_TYPE_PATTERN: str = r"^\s*(?:DECIMAL|NUMERIC)\b"
NUMBER_DECIMAL_REPORTED_TYPE: str = "NUMERIC"
BOOLEAN_TYPE_MARKER: str = "BOOL"
TEMPORAL_TYPE_PATTERN: str = r"^\s*(?:DATE|TIME)"
INSERT_KEYWORD: str = "INSERT"
SQLITE_VIEW_TYPE: str = "view"
SQLITE_TABLE_TYPE: str = "table"
IDENTIFIER_QUOTE: str = '"'
MAIN_SCHEMA_PREFIX: str = "main."
BASE_TABLE_RELATION_TYPE: str = "BASE TABLE"
VIEW_RELATION_TYPE: str = "VIEW"
VIEW_BODY_PATTERN: str = (
    r"^\s*CREATE\s+(?:TEMP\s+|TEMPORARY\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?:\"(?:[^\"]|\"\")+\"|\[[^\]]+\]|`[^`]+`|[^\s(]+)\s*(?:\([^)]*\)\s*)?AS\s+(.*)$"
)

VERSION_TOO_OLD_CODE: str = "A701"
DATABASE_LOCKED_CODE: str = "A702"
INVALID_CONNECTION_CODE: str = "A703"
INVALID_SCHEMA_NAME_CODE: str = "A704"
UNSUPPORTED_FEATURE_CODE: str = "A705"
RELATION_NAME_COLLISION_CODE: str = "A706"
TIMESTAMP_TEXT_FORMAT: str = "%Y-%m-%d %H:%M:%S"
DATE_TIME_PATTERN: str = r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"
