//! Reachability over the review graph.

use std::collections::{BTreeMap, BTreeSet};

use crate::review_command::models::ReviewGraph;

/// Every node reachable downstream from `roots`, including the roots.
pub(crate) fn descendants(graph: &ReviewGraph, roots: &BTreeSet<String>) -> BTreeSet<String> {
    let mut reached: BTreeSet<String> = BTreeSet::new();
    let mut pending: Vec<String> = roots.iter().cloned().collect();
    while let Some(name) = pending.pop() {
        if !reached.insert(name.clone()) {
            continue;
        }
        if let Some(next) = graph.downstream.get(&name) {
            pending.extend(next.iter().cloned());
        }
    }
    reached
}

/// Each node's direct upstream nodes.
pub(crate) fn upstream_of(graph: &ReviewGraph) -> BTreeMap<&str, Vec<&str>> {
    let mut upstream: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
    for (name, children) in &graph.downstream {
        for child in children {
            upstream
                .entry(child.as_str())
                .or_default()
                .push(name.as_str());
        }
    }
    upstream
}

/// The nodes of `within` from which some node of `targets` is reachable, including the targets.
pub(crate) fn ancestors_within(
    graph: &ReviewGraph,
    targets: &BTreeSet<String>,
    within: &BTreeSet<String>,
) -> BTreeSet<String> {
    let upstream: BTreeMap<&str, Vec<&str>> = upstream_of(graph);
    let mut reached: BTreeSet<String> = BTreeSet::new();
    let mut pending: Vec<&str> = targets.iter().map(String::as_str).collect();
    while let Some(name) = pending.pop() {
        if !within.contains(name) || !reached.insert(name.to_owned()) {
            continue;
        }
        if let Some(parents) = upstream.get(name) {
            pending.extend(parents.iter().copied());
        }
    }
    reached
}
