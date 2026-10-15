//! `canonical_event_id`: the required stable id of a known or opaque lifecycle event.

use crate::execution_history::constants::MISSING_EVENT_ID;
use crate::execution_history::errors::{HistoryError, HistoryErrorKind};

/// The event's `event_id` when it is a non-empty string.
pub fn canonical_event_id(event_id: Option<&str>) -> Result<String, HistoryError> {
    match event_id {
        Some(event_id) if !event_id.is_empty() => Ok(event_id.to_owned()),
        _ => Err(HistoryError::new(
            HistoryErrorKind::InvalidEvent,
            MISSING_EVENT_ID,
        )),
    }
}
