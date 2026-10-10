//! Fixed names and tables of native compiler checks.

use polyglot_sql::DialectType;

/// The adapters whose function types are checked, with the dialect name and parser of each.
pub(crate) const FUNCTION_TYPE_DIALECTS: [(&str, &str, DialectType); 4] = [
    ("duckdb", "duckdb", DialectType::DuckDB),
    ("bigquery", "bigquery", DialectType::BigQuery),
    ("snowflake", "snowflake", DialectType::Snowflake),
    ("databricks", "databricks", DialectType::Databricks),
];
/// `to_dict()` fields the CTE alias walk reads.
pub(crate) const CTES_FIELD: &str = "ctes";
pub(crate) const ALIAS_FIELD: &str = "alias";
pub(crate) const NAME_FIELD: &str = "name";
