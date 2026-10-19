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
