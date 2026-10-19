//! `event_row`: the `recall_events` row of one lifecycle event's canonical JSON.

use serde_json::{Map, Value};

use crate::records::_helpers::events::{envelope_columns, event_object, payload_columns};
use crate::records::_helpers::rows::finish_row;
use crate::records::errors::RecordError;
use crate::records::models::{RecallRow, RowEnvelope};
use crate::schema::models::Table;

/// The row of one event, as `lifecycle_event_to_json` encodes it.
pub fn event_row(envelope: &RowEnvelope, event_json: &str) -> Result<RecallRow, RecordError> {
    let event: Map<String, Value> = event_object(event_json)?;
    let mut columns = envelope_columns(&event)?;
    let empty: Map<String, Value> = Map::new();
    let payload = event
        .get("payload")
        .and_then(Value::as_object)
        .unwrap_or(&empty);
    columns.extend(payload_columns(payload));
    Ok(finish_row(Table::Events, envelope, columns))
}
