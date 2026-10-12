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

/// The branch before a node's last child.
pub const TREE_BRANCH_LAST: &str = "└── ";
/// The branch before every other child.
pub const TREE_BRANCH_MID: &str = "├── ";
/// The indent under a last child.
pub const TREE_CONTINUATION_LAST: &str = "    ";
/// The indent under every other child.
pub const TREE_CONTINUATION_MID: &str = "│   ";
