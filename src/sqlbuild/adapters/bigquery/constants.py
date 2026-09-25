"""BigQuery adapter constants."""

BOOLEAN_METADATA_TYPE_NAME: str = "BOOLEAN"
BOOLEAN_WIRE_TYPE_NAME: str = "BOOL"
BIGNUMERIC_TYPE_NAME: str = "BIGNUMERIC"
CUSTOM_NORMALIZATION_TYPE_NAMES: frozenset[str] = frozenset({"INT64", "FLOAT64", "BIGNUMERIC"})
DATE_TYPE_NAME: str = "DATE"
DATETIME_TYPE_NAME: str = "DATETIME"
DECIMAL_METADATA_TYPE_NAMES: frozenset[str] = frozenset({"NUMERIC", "BIGNUMERIC"})
FLOAT_METADATA_TYPE_NAME: str = "FLOAT"
FLOAT_WIRE_TYPE_NAME: str = "FLOAT64"
INTEGER_METADATA_TYPE_NAME: str = "INTEGER"
INTEGER_PARSE_TYPE_NAMES: frozenset[str] = frozenset({"INT", "BIGINT"})
INTEGER_TYPE_TOKEN: str = "INT"
INTEGER_WIRE_TYPE_NAME: str = "INT64"
NOT_FOUND_ERROR_CLASS_NAME: str = "NotFound"
SELECT_STATEMENT_TYPE: str = "SELECT"
TABLE_NAME_WILDCARD: str = "*"
TIMESTAMP_TYPE_TOKEN: str = "TIMESTAMP"

CLONE_REFUSAL_ERROR_CODE: int = 400
CLONE_REFUSAL_REASONS: frozenset[str] = frozenset({"invalid", "invalidQuery"})
CLONE_REFUSAL_PHRASES: tuple[str, ...] = (
    "cannot clone",
    "can't clone",
    "clone is not supported",
    "clones are not supported",
    "cloning is not supported",
    "not supported for clone",
    "clones and snapshots",
    "clone or snapshot",
)
MAX_CLONE_REFUSAL_ERROR_CHAIN: int = 8
