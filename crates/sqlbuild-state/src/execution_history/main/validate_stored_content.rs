//! `validate_stored_content`: an already stored event must hold the same canonical content.

use sqlbuild_core::text::main::python_str_repr::python_str_repr;

use crate::execution_history::errors::{HistoryError, HistoryErrorKind};
use crate::execution_history::models::PreparedEvent;

/// Reject a stored `(content_digest, payload_json)` that differs from the prepared event.
pub fn validate_stored_content(
    prepared: &PreparedEvent,
    (stored_digest, stored_payload): (Option<&str>, Option<&str>),
) -> Result<(), HistoryError> {
    if stored_digest == Some(prepared.digest.as_str())
        && stored_payload == Some(prepared.content.as_str())
    {
        return Ok(());
    }
    Err(HistoryError::new(
        HistoryErrorKind::IntegrityConflict,
        format!(
            "event_id {} has different canonical content",
            python_str_repr(&prepared.event_id)
        ),
    ))
}
