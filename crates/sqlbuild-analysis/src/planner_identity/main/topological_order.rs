//! Stable dependency order with Kahn's algorithm, smallest `(kind, name)` first.

use std::cmp::Reverse;
use std::collections::{BinaryHeap, HashMap};

use crate::planner_identity::_helpers::cycle_message::cycle_message;
use crate::planner_identity::_helpers::dependency_counts::{DependencyCounts, dependency_counts};
use crate::planner_identity::models::GraphKey;

/// Every key in dependency order, or the dependency-cycle message naming the keys left over and the injected edges between them.
pub fn topological_order(
    upstream: &[(GraphKey, Vec<GraphKey>)],
    injected_edge_origins: &HashMap<(GraphKey, GraphKey), String>,
) -> Result<Vec<GraphKey>, String> {
    let DependencyCounts {
        node_keys,
        mut indegree,
        downstream,
    } = dependency_counts(upstream);
    let mut ready: BinaryHeap<Reverse<&GraphKey>> = indegree
        .iter()
        .filter(|(_, count)| **count == 0)
        .map(|(key, _)| Reverse(*key))
        .collect();
    let mut ordered: Vec<GraphKey> = Vec::with_capacity(node_keys.len());
    while let Some(Reverse(current)) = ready.pop() {
        ordered.push(current.clone());
        for downstream_key in downstream.get(current).into_iter().flatten() {
            if let Some(count) = indegree.get_mut(downstream_key) {
                *count = count.saturating_sub(1);
                if *count == 0 {
                    ready.push(Reverse(downstream_key));
                }
            }
        }
    }
    if ordered.len() == node_keys.len() {
        return Ok(ordered);
    }
    Err(cycle_message(
        &ordered,
        node_keys,
        (upstream, injected_edge_origins),
    ))
}
