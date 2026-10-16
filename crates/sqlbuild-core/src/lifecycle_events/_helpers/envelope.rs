//! The catalogue definition and correlations of one event envelope.

use crate::lifecycle_events::main::catalog::catalog;
use crate::lifecycle_events::models::{EventDefinition, KnownEventFacts};

/// Whether the named correlation field is set on the event.
pub(crate) fn correlation_set(event: &KnownEventFacts, name: &str) -> bool {
    event
        .correlations
        .iter()
        .any(|(field, set)| *field == name && *set)
}

/// The catalogue definition of the event's type and schema version, if catalogued.
pub(crate) fn definition(event: &KnownEventFacts) -> Option<EventDefinition> {
    let entries: Vec<EventDefinition> = catalog(event.schema_version)?;
    entries
        .into_iter()
        .find(|entry| entry.event_type == event.event_type)
}
