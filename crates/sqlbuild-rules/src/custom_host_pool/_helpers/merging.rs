//! Host slice merging steps.

use std::collections::{BTreeMap, BTreeSet, HashMap};

use crate::custom_host_pool::constants::MAX_TRACKED_READS;
use crate::custom_host_pool::models::{HostEvaluation, HostSlice};
use crate::custom_host_pool::types::{FactKey, HostInvocation};

/// Untrack evaluations of untracked rules, keeping each invocation's first position.
pub(crate) fn demoted(
    evaluations: Vec<HostEvaluation>,
    untracked: &BTreeSet<String>,
    mut untracked_reads: BTreeMap<String, BTreeSet<FactKey>>,
) -> (Vec<HostEvaluation>, BTreeMap<String, BTreeSet<FactKey>>) {
    let mut evaluated: Vec<HostEvaluation> = Vec::new();
    let mut positions: HashMap<HostInvocation, usize> = HashMap::new();
    for mut evaluation in evaluations {
        if untracked.contains(&evaluation.code)
            && let Some(reads) = evaluation.reads.take()
        {
            untracked_reads
                .entry(evaluation.code.clone())
                .or_default()
                .extend(reads);
        }
        let key: HostInvocation = (evaluation.code.clone(), evaluation.subject.clone());
        match positions.get(&key) {
            Some(index) => evaluated[*index] = evaluation,
            None => {
                positions.insert(key, evaluated.len());
                evaluated.push(evaluation);
            }
        }
    }
    (evaluated, untracked_reads)
}

/// Each observed digest, forgetting any two hosts observed differently.
pub(crate) fn merged_observations(slices: &[HostSlice]) -> BTreeMap<FactKey, Option<String>> {
    let mut observed: BTreeMap<FactKey, Option<String>> = BTreeMap::new();
    for slice in slices {
        for (key, digest) in &slice.observed {
            match observed.get(key) {
                Some(seen) if seen != digest => {
                    observed.insert(key.clone(), None);
                }
                Some(_) => {}
                None => {
                    observed.insert(key.clone(), digest.clone());
                }
            }
        }
    }
    observed
}

/// Every slice's evaluations in single-host order, and the rules reported or demoted untracked.
pub(crate) fn ordered_evaluations(
    slices: &[HostSlice],
    order: &[HostInvocation],
) -> (Vec<HostEvaluation>, BTreeSet<String>) {
    let positions: HashMap<&HostInvocation, usize> = order
        .iter()
        .enumerate()
        .map(|(index, invocation)| (invocation, index))
        .collect();
    let mut evaluations: Vec<HostEvaluation> = Vec::new();
    let mut untracked: BTreeSet<String> = BTreeSet::new();
    for slice in slices {
        evaluations.extend(slice.evaluations.iter().cloned());
        untracked.extend(slice.untracked_reads.keys().cloned());
    }
    if slices.len() > 1 {
        evaluations.sort_by_key(|evaluation| {
            positions
                .get(&(evaluation.code.clone(), evaluation.subject.clone()))
                .copied()
                .unwrap_or(order.len())
        });
    }
    let tracked: BTreeSet<&Vec<FactKey>> = evaluations
        .iter()
        .filter(|evaluation| !untracked.contains(&evaluation.code))
        .filter_map(|evaluation| evaluation.reads.as_ref())
        .collect();
    let tracked_reads: usize = tracked.iter().map(|reads| reads.len()).sum();
    if slices.iter().any(|slice| slice.bounded) || tracked_reads > MAX_TRACKED_READS {
        untracked.extend(
            evaluations
                .iter()
                .filter(|evaluation| evaluation.reads.is_some())
                .map(|evaluation| evaluation.code.clone()),
        );
    }
    (evaluations, untracked)
}

/// The reads each untracked rule's hosts reported directly.
pub(crate) fn collected_untracked_reads(
    slices: &[HostSlice],
    untracked: &BTreeSet<String>,
) -> BTreeMap<String, BTreeSet<FactKey>> {
    let mut reads: BTreeMap<String, BTreeSet<FactKey>> = untracked
        .iter()
        .map(|code| (code.clone(), BTreeSet::new()))
        .collect();
    for slice in slices {
        for (code, keys) in &slice.untracked_reads {
            reads
                .entry(code.clone())
                .or_default()
                .extend(keys.iter().cloned());
        }
    }
    reads
}
