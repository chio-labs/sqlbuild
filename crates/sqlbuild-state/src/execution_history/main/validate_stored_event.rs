//! `validate_stored_event`: a stored event's position, cursor and UTC receipt time.

use crate::execution_history::constants::FIRST_POSITION;
use crate::execution_history::errors::{HistoryError, HistoryErrorKind};

/// A positive `storage_order`, a non-empty cursor and a `received_at` in `UTC`.
pub fn validate_stored_event(
    storage_order: i64,
    cursor: &str,
    received_at_is_utc: bool,
) -> Result<(), HistoryError> {
    let message: Option<&str> = if storage_order < FIRST_POSITION {
        Some("storage_order must be a positive integer")
    } else if cursor.is_empty() {
        Some("event cursor must be non-empty")
    } else if !received_at_is_utc {
        Some("received_at must use UTC")
    } else {
        None
    };
    match message {
        Some(message) => Err(HistoryError::new(
            HistoryErrorKind::ProjectionConsistency,
            message,
        )),
        None => Ok(()),
    }
}
