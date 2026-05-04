"""Adapter shared constants."""

INTEGER_TYPE_NAMES: frozenset[str] = frozenset(
    {"TINYINT", "SMALLINT", "INT", "INTEGER", "BIGINT", "LONG", "INT64"}
)
DECIMAL_TYPE_NAMES: frozenset[str] = frozenset(
    {"DECIMAL", "BIGDECIMAL", "NUMERIC", "NUMBER", "BIGNUMERIC"}
)
FLOAT_TYPE_NAMES: frozenset[str] = frozenset({"DOUBLE", "FLOAT", "FLOAT64", "REAL"})
STRING_TYPE_NAMES: frozenset[str] = frozenset({"VARCHAR", "CHAR", "CHARACTER", "TEXT", "STRING"})
BOOLEAN_TYPE_NAMES: frozenset[str] = frozenset({"BOOLEAN", "BOOL"})
TIMESTAMP_TYPE_NAMES: frozenset[str] = frozenset(
    {"TIMESTAMP", "TIMESTAMPTZ", "TIMESTAMPNTZ", "TIMESTAMPLTZ"}
)
