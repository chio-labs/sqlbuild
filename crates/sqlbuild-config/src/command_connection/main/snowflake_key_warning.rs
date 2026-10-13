//! The warning for Snowflake-like keys in a DuckDB connection.

use crate::command_connection::constants::{DUCKDB_ADAPTER, SNOWFLAKE_LIKE_KEYS};

/// The warning line, when the DuckDB adapter got Snowflake-like connection keys.
#[must_use]
pub fn snowflake_key_warning(adapter_name: &str, keys: &[String]) -> Option<String> {
    if adapter_name != DUCKDB_ADAPTER {
        return None;
    }
    let mut suspicious: Vec<&str> = keys
        .iter()
        .map(String::as_str)
        .filter(|key| SNOWFLAKE_LIKE_KEYS.contains(key))
        .collect();
    if suspicious.is_empty() {
        return None;
    }
    suspicious.sort_unstable();
    Some(format!(
        "Warning: DuckDB adapter is active, but connection contains Snowflake-like keys: {}. If this is a Snowflake local config, add `adapter = \"snowflake\"` at the top of sqlbuild_local.toml, before any section.",
        suspicious.join(", ")
    ))
}
