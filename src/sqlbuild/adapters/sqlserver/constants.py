"""SQL Server adapter constants."""

BOOLEAN_RETURN_TYPE: str = "BIT"
DIFF_CHARACTER_LENGTH_TYPES: frozenset[str] = frozenset(
    {"binary", "char", "nchar", "nvarchar", "varbinary", "varchar"}
)
DIFF_DATETIME_PRECISION_TYPES: frozenset[str] = frozenset({"datetime2", "datetimeoffset", "time"})
DIFF_NUMERIC_PRECISION_TYPES: frozenset[str] = frozenset({"decimal", "numeric"})
DIFF_UNSUPPORTED_COMPARISON_TYPES: frozenset[str] = frozenset(
    {"geography", "geometry", "hierarchyid", "image", "ntext", "text", "xml"}
)
EMPTY_SEED_VALUE: str = ""
INFORMATION_SCHEMA_NULLABLE_VALUE: str = "YES"
INTEGER_TYPE_TOKEN: str = "INT"
