//! `producer_version_problem`: the producer version rule of a lifecycle event.

use crate::lifecycle_events::constants::DEFAULT_PRODUCER;

/// The rule a lifecycle event's producer breaks: other producers must name their version.
#[must_use]
pub fn producer_version_problem(producer: Option<&str>, has_version: bool) -> Option<&'static str> {
    (producer != Some(DEFAULT_PRODUCER) && !has_version)
        .then_some("producer_version is required when producer is not 'sqlbuild'")
}
