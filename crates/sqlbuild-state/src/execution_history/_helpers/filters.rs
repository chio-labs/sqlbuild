//! Filter field checks shared by event and run filters.

use sqlbuild_core::text::main::python_strip::python_strip;

use crate::execution_history::errors::{HistoryError, HistoryErrorKind};
use crate::execution_history::models::FilterTime;

/// An `InvalidFilterError`.
pub(crate) fn filter_error(message: &str) -> HistoryError {
    HistoryError::new(HistoryErrorKind::InvalidFilter, message)
}

/// An optional correlation value must not be blank.
pub(crate) fn filled_text(value: Option<&str>, field_name: &str) -> Result<(), HistoryError> {
    match value {
        Some(value) if python_strip(value).is_empty() => Err(filter_error(&format!(
            "{field_name} must be non-empty when provided"
        ))),
        _ => Ok(()),
    }
}

/// An optional bound must use `UTC`.
pub(crate) fn utc_bound(value: Option<&FilterTime>, field_name: &str) -> Result<(), HistoryError> {
    match value {
        Some(value) if !value.is_utc => Err(filter_error(&format!("{field_name} must use UTC"))),
        _ => Ok(()),
    }
}

/// Both bounds, when present, must not be reversed.
pub(crate) fn bounds_ordered(
    (start, end): (Option<&FilterTime>, Option<&FilterTime>),
    message: &str,
) -> Result<(), HistoryError> {
    match (start, end) {
        (Some(start), Some(end)) if start.instant > end.instant => Err(filter_error(message)),
        _ => Ok(()),
    }
}
