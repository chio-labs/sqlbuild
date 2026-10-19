//! `conflict_row`: evidence that a record key was reused with different content.

use crate::records::_helpers::rows::{finish_row, text};
use crate::records::models::{RecallRow, RowEnvelope};
use crate::schema::models::Table;

/// A `recall_conflicts` row; the first stored row is kept and the rejected digest recorded.
#[must_use]
pub fn conflict_row(
    envelope: &RowEnvelope,
    (dataset, record_key): (&str, &str),
    (existing_sha256, rejected_sha256): (&str, &str),
    detected_at: &str,
) -> RecallRow {
    finish_row(
        Table::Conflicts,
        envelope,
        vec![
            ("dataset", text(dataset)),
            ("record_key", text(record_key)),
            ("existing_sha256", text(existing_sha256)),
            ("rejected_sha256", text(rejected_sha256)),
            ("detected_at", text(detected_at)),
        ],
    )
}
