//! `meta_row`: one insert-only store metadata fact.

use crate::records::_helpers::rows::{finish_row, text};
use crate::records::models::{RecallRow, RowEnvelope};
use crate::schema::models::Table;

/// A `recall_meta` row.
#[must_use]
pub fn meta_row(
    envelope: &RowEnvelope,
    (component, key, value): (&str, &str, &str),
    recorded_at: &str,
) -> RecallRow {
    finish_row(
        Table::Meta,
        envelope,
        vec![
            ("component", text(component)),
            ("key", text(key)),
            ("value", text(value)),
            ("recorded_at", text(recorded_at)),
        ],
    )
}
