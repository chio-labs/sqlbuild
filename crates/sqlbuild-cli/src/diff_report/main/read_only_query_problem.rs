//! Whether one parsed raw diff query is a single read-only expression.

use crate::diff_report::_helpers::request_rules::user_error;
use crate::diff_report::constants::{MUTATING_QUERY_KEYS, READ_ONLY_QUERY_ROOT_KEYS};
use crate::diff_report::errors::DiffUserError;
use crate::diff_report::models::QueryShapeFacts;

/// A non-query root (C235), any data-changing node (C240), or an `INTO`/lock clause (C244).
pub fn read_only_query_problem(label: &str, shape: &QueryShapeFacts) -> Result<(), DiffUserError> {
    if !READ_ONLY_QUERY_ROOT_KEYS.contains(&shape.root_key.as_str()) {
        return Err(user_error(
            &format!("{label} query must be one read-only SELECT, WITH, or VALUES expression"),
            "C235",
        ));
    }
    if shape
        .node_keys
        .iter()
        .any(|key| MUTATING_QUERY_KEYS.contains(&key.as_str()))
    {
        return Err(user_error(
            &format!("{label} query must not contain data-changing or administrative statements"),
            "C240",
        ));
    }
    if shape.writes_or_locks {
        return Err(user_error(
            &format!("{label} query must not write a relation or acquire row locks"),
            "C244",
        ));
    }
    Ok(())
}
