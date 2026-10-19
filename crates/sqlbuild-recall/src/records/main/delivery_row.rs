//! `delivery_row`: the final accounting of one stream, written last.

use crate::records::_helpers::rows::{boolean, finish_row, integer, text};
use crate::records::models::{DeliveryCounts, RecallRow, RowEnvelope};
use crate::schema::models::Table;

/// The delivery row of `stream`.
#[must_use]
pub fn delivery_row(
    envelope: &RowEnvelope,
    stream: &str,
    (counts, flush_complete): (&DeliveryCounts, bool),
    written_at: &str,
) -> RecallRow {
    finish_row(
        Table::Delivery,
        envelope,
        vec![
            ("stream", text(stream)),
            ("accepted", integer(counts.accepted)),
            ("delivered", integer(counts.delivered)),
            ("filtered", integer(counts.filtered)),
            ("dropped", integer(counts.dropped)),
            ("failed", integer(counts.failed)),
            ("conflicts", integer(counts.conflicts)),
            ("flush_complete", boolean(flush_complete)),
            ("written_at", text(written_at)),
        ],
    )
}
