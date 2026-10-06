//! Lexical quoting facts of the SQL dialects the rules engine scans.

use crate::sql_scan::models::QuotePolicy;
use sqlparser::dialect::{
    BigQueryDialect, ClickHouseDialect, DatabricksDialect, Dialect, DuckDbDialect, GenericDialect,
    MsSqlDialect, PostgreSqlDialect, SnowflakeDialect,
};

pub(crate) fn rules_quote_policy(dialect_name: &str) -> QuotePolicy {
    let dialect = rules_dialect(dialect_name);
    let backslash_escapes = dialect.supports_string_literal_backslash_escape();
    QuotePolicy {
        backtick_identifiers: dialect.is_delimited_identifier_start('`'),
        single_quote_backslash_escapes: backslash_escapes,
        double_quote_backslash_escapes: backslash_escapes
            && !dialect.is_delimited_identifier_start('"'),
        dollar_quotes: false,
    }
}

pub(crate) fn rules_dialect(name: &str) -> Box<dyn Dialect> {
    match name.to_ascii_lowercase().as_str() {
        "bigquery" => Box::new(BigQueryDialect {}),
        "clickhouse" => Box::new(ClickHouseDialect {}),
        "databricks" => Box::new(DatabricksDialect {}),
        "duckdb" => Box::new(DuckDbDialect {}),
        "postgres" | "postgresql" => Box::new(PostgreSqlDialect {}),
        "mssql" | "sqlserver" | "tsql" => Box::new(MsSqlDialect {}),
        "snowflake" => Box::new(SnowflakeDialect {}),
        _ => Box::new(GenericDialect {}),
    }
}
