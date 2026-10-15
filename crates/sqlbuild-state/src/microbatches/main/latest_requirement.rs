//! `latest_requirement`: the newest replay requirement created for the compiled version.

use std::cmp::Ordering;

use crate::microbatches::models::RequirementFact;

/// The index of the first event ordering last by creation time then event ID, if any.
#[must_use]
pub fn latest_requirement(events: &[RequirementFact], current: &str) -> Option<usize> {
    let mut best: Option<usize> = None;
    for (index, event) in events.iter().enumerate() {
        if !event.is_requirement || event.required_model_version_hash.as_deref() != Some(current) {
            continue;
        }
        let newer: bool = best.is_none_or(|best| {
            let held: &RequirementFact = &events[best];
            event
                .created
                .partial_cmp(&held.created)
                .unwrap_or(Ordering::Equal)
                .then_with(|| event.event_id.cmp(&held.event_id))
                == Ordering::Greater
        });
        if newer {
            best = Some(index);
        }
    }
    best
}
