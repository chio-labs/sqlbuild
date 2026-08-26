"""Adapter constants."""

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
DATE_TYPE_NAME: str = "DATE"
DATETIME_TYPE_NAME: str = "DATETIME"
POLYGLOT_CUSTOM_TYPE_NAME: str = "CUSTOM"
TIMESTAMP_TYPE_TOKEN: str = "TIMESTAMP"
INTEGER_TYPE_TOKEN: str = "INT"
TYPED_OBJECT_ENTRY_PART_COUNT: int = 2
TABLE_RELATION_TYPE_NAMES: frozenset[str] = frozenset(
    {"base table", "table", "managed", "external"}
)
VIEW_RELATION_TYPE_NAMES: frozenset[str] = frozenset({"view", "base view"})
DIFF_LEFT_SIDE: str = "left"
DIFF_RIGHT_SIDE: str = "right"
QUALIFIED_NAME_SEPARATOR: str = "."
PYTHON_INIT_FILE_NAME: str = "__init__.py"
PYTHON_IDENTIFIER_REPLACEMENT: str = "_"
