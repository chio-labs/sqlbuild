//! How many hosts a run is worth.

use crate::custom_host_pool::constants::MAX_HOSTS;

/// One host per `min_invocations_per_host` invocations, bounded by cores and eight, at least one.
#[must_use]
pub fn host_count(invocations: usize, (cores, min_invocations_per_host): (usize, usize)) -> usize {
    MAX_HOSTS
        .min(cores)
        .min(invocations / min_invocations_per_host.max(1))
        .max(1)
}
