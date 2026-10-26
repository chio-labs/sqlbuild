"""MotherDuck adapter constants."""

EMPTY_CONNECTION_VALUE: str = ""
URI_QUERY_SEPARATOR: str = "?"
URI_ADDITIONAL_PARAMETER_SEPARATOR: str = "&"
MOTHERDUCK_UNSUPPORTED_DUCKDB_MARKER: str = "is not yet supported by MotherDuck"
MOTHERDUCK_UNSUPPORTED_DUCKDB_HELP: str = (
    "This SQLBuild release requires DuckDB 2.0. To use MotherDuck, stay on SQLBuild 0.182.0, "
    "the last release that supports DuckDB 1.5, until MotherDuck supports DuckDB 2.0."
)
