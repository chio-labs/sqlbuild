//! The flat `compile_timings` entries of one custom-rule evaluation.

use std::collections::{BTreeMap, BTreeSet};

use crate::custom_host_pool::constants::{
    CUSTOM_RULE_KEY_PREFIX, CUSTOM_RULES_GUARD_KEY, CUSTOM_RULES_INVOCATIONS_KEY,
    CUSTOM_RULES_MONITOR_KEY, NANOSECONDS_PER_MILLISECOND,
};
use crate::custom_host_pool::models::{HostTimings, RuleTiming};

/// Run-wide totals, then each rule's invocations, CPU and cache counts in code order.
#[must_use]
pub fn custom_rule_timings(
    timings: &HostTimings,
    cache_counts: &BTreeMap<String, (usize, usize)>,
) -> Vec<(String, u64)> {
    let invocations: u64 = timings
        .rules
        .values()
        .map(|timing| timing.invocations)
        .sum();
    let mut entries: Vec<(String, u64)> = vec![
        (CUSTOM_RULES_INVOCATIONS_KEY.to_owned(), invocations),
        (
            CUSTOM_RULES_MONITOR_KEY.to_owned(),
            timings.monitor_ns / NANOSECONDS_PER_MILLISECOND,
        ),
        (
            CUSTOM_RULES_GUARD_KEY.to_owned(),
            timings.guard_ns / NANOSECONDS_PER_MILLISECOND,
        ),
    ];
    let codes: BTreeSet<&String> = timings.rules.keys().chain(cache_counts.keys()).collect();
    for code in codes {
        let timing: RuleTiming = timings.rules.get(code).copied().unwrap_or_default();
        let (hits, misses): (usize, usize) = cache_counts.get(code).copied().unwrap_or_default();
        let key = |measure: &str| format!("{CUSTOM_RULE_KEY_PREFIX}{code}.{measure}");
        entries.extend([
            (key("invocations"), timing.invocations),
            (key("cpu_ms"), timing.cpu_ns / NANOSECONDS_PER_MILLISECOND),
            (key("cache_hits"), u64::try_from(hits).unwrap_or(u64::MAX)),
            (
                key("cache_misses"),
                u64::try_from(misses).unwrap_or(u64::MAX),
            ),
        ]);
    }
    entries
}
