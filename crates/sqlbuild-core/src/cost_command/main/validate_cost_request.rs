//! The limit, sort and bound checks of a cost request.

use crate::cost_command::constants::{
    BREAKDOWN_SORT_FIELDS, HISTORY_SELECTOR, HISTORY_SORT_FIELDS,
};
use crate::cost_command::errors::CostCommandError;

/// Refuse a bad limit, then an unknown sort field or `--since`/`--until` outside history.
pub fn validate_cost_request(
    selector: &str,
    (limit, no_limit): (Option<i64>, bool),
    sort_field: &str,
    has_bounds: bool,
) -> Result<(), CostCommandError> {
    if limit.is_some_and(|limit| limit < 0) {
        return Err(CostCommandError::new(
            "C709",
            "cost --limit must be non-negative",
        ));
    }
    if no_limit && limit.is_some() {
        return Err(CostCommandError::new(
            "C710",
            "cost --limit and --no-limit cannot be combined",
        ));
    }
    if selector == HISTORY_SELECTOR {
        if !HISTORY_SORT_FIELDS.contains(&sort_field) {
            return Err(CostCommandError::new(
                "C701",
                format!(
                    "cost history --sort must be one of: {}",
                    HISTORY_SORT_FIELDS.join(", ")
                ),
            ));
        }
        return Ok(());
    }
    if has_bounds {
        return Err(CostCommandError::new(
            "C702",
            "--since and --until are only valid for cost history",
        ));
    }
    if !BREAKDOWN_SORT_FIELDS.contains(&sort_field) {
        return Err(CostCommandError::new(
            "C703",
            format!(
                "cost --sort must be one of: {}",
                BREAKDOWN_SORT_FIELDS.join(", ")
            ),
        ));
    }
    Ok(())
}
