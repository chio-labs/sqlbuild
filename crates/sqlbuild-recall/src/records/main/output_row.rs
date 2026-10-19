//! `output_row`: the `recall_output` row of one chunk.

use crate::records::_helpers::ids::output_record_id;
use crate::records::_helpers::rows::{finish_row, integer, text};
use crate::records::constants::{
    DROPPED_BEFORE_COLUMN, OMITTED_BYTES_COLUMN, OMITTED_SEQUENCES_COLUMN,
};
use crate::records::models::{OutputChunk, RecallRow, RecallValue, RowEnvelope};
use crate::schema::models::Table;

/// The row of `chunk`, keyed by invocation and sequence.
#[must_use]
pub fn output_row(envelope: &RowEnvelope, chunk: &OutputChunk) -> RecallRow {
    finish_row(
        Table::Output,
        envelope,
        vec![
            (
                "record_id",
                text(output_record_id(&envelope.invocation_id, chunk.sequence)),
            ),
            ("sequence", integer(chunk.sequence)),
            ("stream", text(chunk.stream.as_str())),
            ("occurred_at", text(&chunk.occurred_at)),
            ("data", RecallValue::Blob(chunk.data.clone())),
            ("byte_offset", integer(chunk.byte_offset)),
            ("byte_count", integer(chunk.data.len() as u64)),
            ("priority", text("output")),
            (DROPPED_BEFORE_COLUMN, integer(chunk.dropped_before)),
            (
                OMITTED_BYTES_COLUMN,
                chunk
                    .omitted
                    .map_or(RecallValue::Null, |omitted| integer(omitted.bytes)),
            ),
            (
                OMITTED_SEQUENCES_COLUMN,
                chunk
                    .omitted
                    .map_or(RecallValue::Null, |omitted| integer(omitted.sequences)),
            ),
        ],
    )
}
