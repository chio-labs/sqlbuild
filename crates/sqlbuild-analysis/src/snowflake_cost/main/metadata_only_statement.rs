//! `metadata_only_statement`: Snowflake statements that run without warehouse compute.

use crate::snowflake_cost::_helpers::statements::{metadata_only_create, of_kind, python_space};
use crate::snowflake_cost::constants::{CREATE_QUERY_TYPE, DROP_QUERY_TYPE, USE_QUERY_TYPE};

/// Identify statements Snowflake executes without warehouse compute.
pub fn metadata_only_statement(query_type: &str, query_text: Option<&str>) -> bool {
    let normalized: String = query_type.to_uppercase().replace(' ', "_");
    if of_kind(&normalized, USE_QUERY_TYPE) || of_kind(&normalized, DROP_QUERY_TYPE) {
        return true;
    }
    if !of_kind(&normalized, CREATE_QUERY_TYPE) {
        return false;
    }
    match query_text {
        Some(text) if !text.chars().all(python_space) => metadata_only_create(text),
        _ => false,
    }
}
