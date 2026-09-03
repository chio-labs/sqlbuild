"""Diagnostic logging policy constants."""

LOGGER_ROOT_NAME: str = "sqlbuild"
LOGGER_PREFIX: str = "sqlbuild."
SQL_DIGEST_FIELD: str = "sqlbuild_sql_digest"
SQL_TEXT_FIELD: str = "sqlbuild_sql"
SQL_PRIVATE_RECORD_FIELD: str = "sqlbuild_private_sql_record"
SQL_PRIVATE_RECORD_MARKER: object = object()
REDACTED_SQL_LOG_MESSAGE: str = "SQL diagnostic omitted"
FORMATTER_RECORD_FIELDS: frozenset[str] = frozenset(("message", "asctime"))
