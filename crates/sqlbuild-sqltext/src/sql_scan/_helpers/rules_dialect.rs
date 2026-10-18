//! Lexical quoting facts of the SQL dialects the rules engine scans.

use crate::sql_scan::models::QuotePolicy;

pub(crate) fn rules_quote_policy(dialect_name: &str) -> QuotePolicy {
    let (backtick_identifiers, backslash_escapes, double_quote_identifiers) =
        match dialect_name.to_ascii_lowercase().as_str() {
            "bigquery" => (true, true, false),
            "clickhouse" | "snowflake" => (true, true, true),
            "postgres" | "postgresql" | "mssql" | "sqlserver" | "tsql" => (false, false, true),
            "databricks" => (true, false, false),
            _ => (true, false, true),
        };
    QuotePolicy {
        backtick_identifiers,
        single_quote_backslash_escapes: backslash_escapes,
        double_quote_backslash_escapes: backslash_escapes && !double_quote_identifiers,
        dollar_quotes: false,
    }
}
