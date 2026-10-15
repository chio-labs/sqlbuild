use crate::lifecycle_events::models::{KnownEventFacts, PayloadValue};

/// An integer payload value.
pub(crate) fn int(value: i128) -> PayloadValue {
    PayloadValue::Integer {
        value,
        text: value.to_string(),
    }
}

/// A text payload value.
pub(crate) fn text(value: &str) -> PayloadValue {
    PayloadValue::Text(value.to_owned())
}

/// A version 2 event of `event_type` with every correlation set.
pub(crate) fn event(event_type: &str, payload: Vec<(&str, PayloadValue)>) -> KnownEventFacts {
    KnownEventFacts {
        schema_version: 2,
        event_type: event_type.to_owned(),
        correlations: vec![
            ("run_id", true),
            ("resource_id", true),
            ("resource_attempt_id", true),
            ("operation_id", true),
            ("statement_id", true),
        ],
        payload: payload
            .into_iter()
            .map(|(key, value)| (key.to_owned(), value))
            .collect(),
    }
}
