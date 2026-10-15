//! How many hosts a run is worth.

use crate::custom_host_pool::constants::{MAX_HOSTS, MIN_INVOCATIONS_PER_HOST};

/// One host per 64 invocations, bounded by usable CPUs and eight, and at least one.
#[must_use]
pub fn host_count(invocations: usize, cores: usize) -> usize {
    MAX_HOSTS
        .min(cores)
        .min(invocations / MIN_INVOCATIONS_PER_HOST)
        .max(1)
}
