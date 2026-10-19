//! `event_row`: the `recall_events` row of one lifecycle event's canonical JSON.

use serde_json::{Map, Value};

use crate::records::_helpers::events::event_object;
use crate::records::errors::RecordError;
use crate::records::main::event_object_row::event_object_row;
use crate::records::models::{RecallRow, RowEnvelope};

/// The row of one event, as `lifecycle_event_to_json` encodes it.
pub fn event_row(envelope: &RowEnvelope, event_json: &str) -> Result<RecallRow, RecordError> {
    let event: Map<String, Value> = event_object(event_json)?;
    event_object_row(envelope, &event)
}
