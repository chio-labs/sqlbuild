//! Function argument and return types checked against the adapter's SQL analysis dialect.

use polyglot_sql::{Dialect, DialectType, ParseOptions};

use crate::lineage::_helpers::parsed_lineage::proxy_parse_options;

/// The adapters whose function types are checked, and the dialect each is parsed with.
const DIALECT_BY_ADAPTER: [(&str, &str, DialectType); 4] = [
    ("duckdb", "duckdb", DialectType::DuckDB),
    ("bigquery", "bigquery", DialectType::BigQuery),
    ("snowflake", "snowflake", DialectType::Snowflake),
    ("databricks", "databricks", DialectType::Databricks),
];

/// The error for a type the adapter's dialect cannot parse; adapters without a dialect pass.
#[must_use]
pub fn function_type_error(type_sql: &str, adapter_name: &str, context: &str) -> Option<String> {
    let (_, dialect_name, dialect) = DIALECT_BY_ADAPTER
        .iter()
        .find(|(adapter, _, _)| *adapter == adapter_name)?;
    let options: ParseOptions = proxy_parse_options().unwrap_or_default();
    let error = Dialect::get(*dialect)
        .parse_data_type_with_options(type_sql, &options)
        .err()?;
    Some(format!(
        "{context} type '{type_sql}' is not valid for adapter '{adapter_name}' SQL analysis \
         dialect '{dialect_name}': {error}"
    ))
}
