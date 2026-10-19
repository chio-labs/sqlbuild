//! `event_severity`: the export severity of a lifecycle event, without building its row.

use serde_json::{Map, Value};

use crate::records::_helpers::events::severity_of;

/// The severity the event's row will carry; `None` when the event has no text `event_type`.
#[must_use]
pub fn event_severity(event: &Map<String, Value>) -> Option<&'static str> {
    severity_of(event)
}
