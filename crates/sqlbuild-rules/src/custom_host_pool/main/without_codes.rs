//! Drop every result a host reported for some rules.

use std::collections::BTreeSet;

use crate::custom_host_pool::models::HostSlice;

/// The slice without evaluations, untracked reads, uncacheable or stateful marks of `codes`.
#[must_use]
pub fn without_codes(slice: HostSlice, codes: &BTreeSet<String>) -> HostSlice {
    HostSlice {
        evaluations: slice
            .evaluations
            .into_iter()
            .filter(|evaluation| !codes.contains(&evaluation.code))
            .collect(),
        untracked_reads: slice
            .untracked_reads
            .into_iter()
            .filter(|(code, _)| !codes.contains(code))
            .collect(),
        uncacheable: slice.uncacheable.difference(codes).cloned().collect(),
        stateful: slice.stateful.difference(codes).cloned().collect(),
        ..slice
    }
}
