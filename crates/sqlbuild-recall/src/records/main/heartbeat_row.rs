//! `heartbeat_row`: one liveness fact of a running invocation.

use crate::records::_helpers::rows::{finish_row, integer, optional_text, text};
use crate::records::models::{RecallRow, RecallValue, RowEnvelope};
use crate::schema::models::Table;

/// A heartbeat at `beat_at` that declares the invocation abandoned after `stale_at`.
#[must_use]
pub fn heartbeat_row(
    envelope: &RowEnvelope,
    (beat_at, stale_at): (&str, &str),
    (host_token, pid): (Option<&str>, Option<u32>),
) -> RecallRow {
    finish_row(
        Table::Heartbeats,
        envelope,
        vec![
            ("beat_at", text(beat_at)),
            ("stale_at", text(stale_at)),
            ("host_token", optional_text(host_token)),
            (
                "pid",
                pid.map_or(RecallValue::Null, |pid| integer(u64::from(pid))),
            ),
        ],
    )
}
