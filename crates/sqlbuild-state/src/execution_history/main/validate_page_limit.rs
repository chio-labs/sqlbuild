//! `validate_page_limit`: a positive storage page limit no greater than the maximum.

use crate::execution_history::constants::MAX_PAGE_LIMIT;
use crate::execution_history::constants::MIN_PAGE_LIMIT;
use crate::execution_history::errors::{HistoryError, HistoryErrorKind};

/// Reject a missing (non-integer) limit or one outside `1..=MAX_PAGE_LIMIT`.
pub fn validate_page_limit(limit: Option<i64>) -> Result<(), HistoryError> {
    match limit {
        Some(limit) if (MIN_PAGE_LIMIT..=MAX_PAGE_LIMIT).contains(&limit) => Ok(()),
        _ => Err(HistoryError::new(
            HistoryErrorKind::InvalidLimit,
            format!("limit must be an integer from 1 through {MAX_PAGE_LIMIT}"),
        )),
    }
}
