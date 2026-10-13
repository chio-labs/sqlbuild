use crate::terminal_events::models::{TerminalFact, TerminalRequest};

/// A terminal of `orders` with an attempt identifier and number.
pub(super) fn attempt(
    event_id: &str,
    event_type: &str,
    (attempt_id, number): (&str, i64),
) -> TerminalFact {
    TerminalFact {
        event_id: event_id.to_owned(),
        event_type: event_type.to_owned(),
        resource_id: Some("model:orders".to_owned()),
        resource_name: Some("orders".to_owned()),
        resource_attempt_id: Some(attempt_id.to_owned()),
        attempt_number: Some(number),
        operation_name: None,
    }
}

/// A fact that only has an identifier and type.
pub(super) fn fact(event_id: &str, event_type: &str) -> TerminalFact {
    TerminalFact {
        event_id: event_id.to_owned(),
        event_type: event_type.to_owned(),
        ..TerminalFact::default()
    }
}

/// A claim for `orders` by name only.
pub(super) fn orders_request() -> TerminalRequest {
    TerminalRequest {
        resource_name: "orders".to_owned(),
        ..TerminalRequest::default()
    }
}
