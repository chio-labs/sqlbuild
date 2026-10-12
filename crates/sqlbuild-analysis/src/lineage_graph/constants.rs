//! Rich lineage dialect aliases.

/// Aliases Python maps before trying the name as a Polyglot dialect value.
pub const ANALYSIS_DIALECT_ALIASES: [(&str, &str); 12] = [
    ("", "generic"),
    ("ansi", "generic"),
    ("generic", "generic"),
    ("bigquery", "bigquery"),
    ("snowflake", "snowflake"),
    ("duckdb", "duckdb"),
    ("motherduck", "duckdb"),
    ("databricks", "databricks"),
    ("postgres", "postgresql"),
    ("tsql", "tsql"),
    ("sqlserver", "tsql"),
    ("postgresql", "postgresql"),
];
