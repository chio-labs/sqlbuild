//! `validate_page`: a page's next cursor must agree with its records.

use crate::execution_history::errors::{HistoryError, HistoryErrorKind};

/// No cursor on an empty page; on an event page, the cursor of its last record.
pub fn validate_page(
    is_event_page: bool,
    has_records: bool,
    (next_cursor, last_cursor): (Option<&str>, Option<&str>),
) -> Result<(), HistoryError> {
    let kind: &str = if is_event_page { "event" } else { "run" };
    if !has_records && next_cursor.is_some() {
        return Err(HistoryError::new(
            HistoryErrorKind::ProjectionConsistency,
            format!("an empty {kind} page cannot have a next cursor"),
        ));
    }
    if is_event_page && has_records && next_cursor != last_cursor {
        return Err(HistoryError::new(
            HistoryErrorKind::ProjectionConsistency,
            "event page cursor must identify its last record",
        ));
    }
    Ok(())
}
