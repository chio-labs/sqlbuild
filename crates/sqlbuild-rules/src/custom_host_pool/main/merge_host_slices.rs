//! Combine host slices exactly as one host would have reported every invocation.

use std::collections::{BTreeMap, BTreeSet};

use crate::custom_host_pool::_helpers::merging::{
    collected_untracked_reads, demoted, merged_observations, ordered_evaluations,
};
use crate::custom_host_pool::models::{HostEvaluation, HostRun, HostSlice};
use crate::custom_host_pool::types::{FactKey, HostInvocation};

/// Merge slices in single-host invocation `order`, demoting tracking that grew too large.
#[must_use]
pub fn merge_host_slices(slices: Vec<HostSlice>, order: &[HostInvocation]) -> HostRun {
    let (evaluations, untracked): (Vec<HostEvaluation>, BTreeSet<String>) =
        ordered_evaluations(&slices, order);
    let untracked_reads: BTreeMap<String, BTreeSet<FactKey>> =
        collected_untracked_reads(&slices, &untracked);
    let (evaluated, untracked_reads): (Vec<HostEvaluation>, BTreeMap<String, BTreeSet<FactKey>>) =
        demoted(evaluations, &untracked, untracked_reads);
    HostRun {
        evaluated,
        untracked_reads: untracked_reads
            .into_iter()
            .map(|(code, reads)| (code, reads.into_iter().collect()))
            .collect(),
        uncacheable: slices
            .iter()
            .flat_map(|slice| slice.uncacheable.iter().cloned())
            .collect(),
        observed: merged_observations(&slices),
    }
}
