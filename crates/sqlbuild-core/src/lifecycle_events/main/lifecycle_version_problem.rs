//! `lifecycle_version_problem`: the schema version and invocation metadata rules of an event.

use crate::lifecycle_events::constants::{
    CURRENT_LIFECYCLE_EVENT_SCHEMA_VERSION, INVOCATION_SEQUENCE_PROBLEM,
    LIFECYCLE_EVENT_SCHEMA_VERSIONS, UNSEQUENCED_SCHEMA_VERSION,
};
use crate::lifecycle_events::models::SequenceFact;

/// The first rule a lifecycle event's schema version and invocation metadata break.
#[must_use]
pub fn lifecycle_version_problem(
    schema_version: i128,
    sequence: SequenceFact,
    has_external_context: bool,
) -> Option<String> {
    let known: bool = LIFECYCLE_EVENT_SCHEMA_VERSIONS
        .iter()
        .any(|version| i128::from(*version) == schema_version);
    if !known {
        return Some(format!(
            "LifecycleEvent only represents known schema versions through \
             {CURRENT_LIFECYCLE_EVENT_SCHEMA_VERSION}; decode other versions as \
             OpaqueLifecycleEvent"
        ));
    }
    if schema_version == UNSEQUENCED_SCHEMA_VERSION {
        return (sequence != SequenceFact::Absent || has_external_context).then(|| {
            "schema version 1 lifecycle events cannot contain invocation metadata".to_owned()
        });
    }
    (sequence != SequenceFact::Valid).then(|| INVOCATION_SEQUENCE_PROBLEM.to_owned())
}
