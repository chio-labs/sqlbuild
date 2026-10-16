//! Stable dependency order with Kahn's algorithm, smallest `(kind, name)` first.

use std::cmp::Reverse;
use std::collections::{BinaryHeap, HashMap};

use sqlbuild_core::graph_walk::main::kahn_order::kahn_order;

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
        indegree,
        downstream,
    } = dependency_counts(upstream);
    let ordered: Vec<GraphKey> = kahn_order(
        (node_keys.iter().copied(), indegree),
        BinaryHeap::<Reverse<&GraphKey>>::new(),
        |current| downstream.get(*current).cloned().unwrap_or_default(),
    )
    .into_iter()
    .cloned()
    .collect();
    if ordered.len() == node_keys.len() {
        return Ok(ordered);
    }
    Err(cycle_message(
        &ordered,
        node_keys,
        (upstream, injected_edge_origins),
    ))
}
