use crate::records::errors::RecordError;
use crate::records::main::event_object_row::event_object_row;
use crate::records::main::parse_event::parse_event;
use crate::records::models::{RecallRow, RecallValue, RowEnvelope};

/// The envelope every record test row shares.
pub(crate) fn envelope() -> RowEnvelope {
    RowEnvelope {
        invocation_id: "inv1".to_owned(),
        invocation_started_at: "2026-10-19T00:00:00.000000Z".to_owned(),
        producer_version: "0.0.0".to_owned(),
    }
}

/// `columns` of `row` paired with their values, when present.
pub(crate) fn row_columns(
    row: &RecallRow,
    columns: &[(&'static str, RecallValue)],
) -> Vec<(&'static str, Option<RecallValue>)> {
    columns
        .iter()
        .map(|(name, _)| (*name, row.value(name).cloned()))
        .collect()
}

/// `expected` in the shape `row_columns` returns.
pub(crate) fn present(
    expected: Vec<(&'static str, RecallValue)>,
) -> Vec<(&'static str, Option<RecallValue>)> {
    expected
        .into_iter()
        .map(|(name, value)| (name, Some(value)))
        .collect()
}

/// A text value.
pub(crate) fn text(value: &str) -> RecallValue {
    RecallValue::Text(value.to_owned())
}

/// The events row of one lifecycle event's canonical JSON, as the delivery thread builds it.
pub(crate) fn event_row(
    envelope: &RowEnvelope,
    event_json: &str,
) -> Result<RecallRow, RecordError> {
    parse_event(event_json).and_then(|event| event_object_row(envelope, &event))
}
