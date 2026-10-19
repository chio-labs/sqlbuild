//! `event_object_row`: the `recall_events` row of one lifecycle event already decoded to JSON.

use serde_json::{Map, Value};

use crate::records::_helpers::events::{envelope_columns, payload_columns};
use crate::records::_helpers::rows::finish_row;
use crate::records::errors::RecordError;
use crate::records::models::{RecallRow, RowEnvelope};
use crate::schema::models::Table;

/// The row of one event given as the object `lifecycle_event_to_json` would encode.
pub fn event_object_row(
    envelope: &RowEnvelope,
    event: &Map<String, Value>,
) -> Result<RecallRow, RecordError> {
    let mut columns = envelope_columns(event)?;
    let empty: Map<String, Value> = Map::new();
    let payload = event
        .get("payload")
        .and_then(Value::as_object)
        .unwrap_or(&empty);
    columns.extend(payload_columns(payload));
    Ok(finish_row(Table::Events, envelope, columns))
}
