//! `validate_known_event`: correlations and safe payload fields of one catalogued event.

use std::collections::BTreeSet;

use crate::lifecycle_events::_helpers::envelope::{correlation_set, definition};
use crate::lifecycle_events::_helpers::payloads::family_problem;
use crate::lifecycle_events::models::KnownEventFacts;
use crate::text::main::python_str_repr::python_str_repr;

/// The first contract violation of a catalogued event, as its validation message.
pub fn validate_known_event(event: &KnownEventFacts) -> Result<(), String> {
    let quoted: String = python_str_repr(&event.event_type);
    let Some(definition) = definition(event) else {
        return Err(format!(
            "unknown lifecycle event_type {quoted}; decode it as an opaque envelope"
        ));
    };
    let missing: Vec<&str> = definition
        .required_correlations
        .iter()
        .copied()
        .filter(|name| !correlation_set(event, name))
        .collect();
    if !missing.is_empty() {
        return Err(format!(
            "known event {quoted} requires correlation field(s): {}",
            missing.join(", ")
        ));
    }
    let keys: BTreeSet<&str> = event.payload.iter().map(|(key, _)| key.as_str()).collect();
    let missing_payload: Vec<&str> = definition
        .required_payload
        .iter()
        .copied()
        .filter(|name| !keys.contains(name))
        .collect();
    if !missing_payload.is_empty() {
        return Err(format!(
            "known event {quoted} requires payload field(s): {}",
            missing_payload.join(", ")
        ));
    }
    let unexpected: Vec<&str> = keys
        .iter()
        .copied()
        .filter(|key| !definition.allowed_payload.contains(key))
        .collect();
    if !unexpected.is_empty() {
        let allowed: String = if definition.allowed_payload.is_empty() {
            "none".to_owned()
        } else {
            definition.allowed_payload.join(", ")
        };
        return Err(format!(
            "payload field(s) not allowed for known event {quoted}: {}; allowed fields: {allowed}",
            unexpected.join(", ")
        ));
    }
    family_problem(event).map_or(Ok(()), Err)
}
