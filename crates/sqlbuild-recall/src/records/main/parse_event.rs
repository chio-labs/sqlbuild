//! `parse_event`: a lifecycle event's canonical JSON as its object.

use serde_json::{Map, Value};

use crate::records::_helpers::events::event_object;
use crate::records::errors::RecordError;

/// The JSON object of one lifecycle event; an error unless `event_json` is a JSON object.
pub fn parse_event(event_json: &str) -> Result<Map<String, Value>, RecordError> {
    event_object(event_json)
}
