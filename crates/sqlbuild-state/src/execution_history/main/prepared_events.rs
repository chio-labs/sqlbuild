//! `prepared_events`: digest a batch and reject ids reused with different content inside it.

use std::collections::HashMap;

use sha2::{Digest, Sha256};
use sqlbuild_core::text::main::python_str_repr::python_str_repr;

use crate::execution_history::errors::{HistoryError, HistoryErrorKind};
use crate::execution_history::models::{EventSubmission, PreparedEvent};

/// Each submission with the SHA-256 hex digest of its content, in order.
pub fn prepared_events(
    submissions: Vec<EventSubmission>,
) -> Result<Vec<PreparedEvent>, HistoryError> {
    let mut digests: HashMap<String, String> = HashMap::new();
    let mut prepared: Vec<PreparedEvent> = Vec::with_capacity(submissions.len());
    for submission in submissions {
        let digest: String = format!("{:x}", Sha256::digest(submission.content.as_bytes()));
        if let Some(previous) = digests.get(&submission.event_id)
            && *previous != digest
        {
            return Err(HistoryError::new(
                HistoryErrorKind::IntegrityConflict,
                format!(
                    "event_id {} has different canonical content within batch",
                    python_str_repr(&submission.event_id)
                ),
            ));
        }
        digests.insert(submission.event_id.clone(), digest.clone());
        prepared.push(PreparedEvent {
            event_id: submission.event_id,
            content: submission.content,
            digest,
            envelope: submission.envelope,
        });
    }
    Ok(prepared)
}
