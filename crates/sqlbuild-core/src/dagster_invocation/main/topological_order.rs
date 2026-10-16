//! DAG node order for emitting Dagster events.

use std::collections::{HashMap, VecDeque};

use crate::dagster_invocation::_helpers::graph::{
    EdgeSets, edge_sets, id_positions, unique_positions,
};
use crate::graph_walk::main::kahn_order::kahn_order;

/// Node positions in Kahn order over known edges, or `None` when a cycle leaves nodes out.
#[must_use]
pub fn topological_order(ids: &[String], edges: &[(String, String)]) -> Option<Vec<usize>> {
    let positions: HashMap<&str, usize> = id_positions(ids);
    let unique: Vec<usize> = unique_positions(ids, &positions);
    let EdgeSets { incoming, outgoing } = edge_sets(&unique, (&positions, edges));
    let remaining: HashMap<usize, usize> = incoming
        .iter()
        .map(|(position, upstream)| (*position, upstream.len()))
        .collect();
    let ordered: Vec<usize> = kahn_order(
        (unique.iter().copied(), remaining),
        VecDeque::new(),
        |position| outgoing.get(position).cloned().unwrap_or_default(),
    );
    (ordered.len() == ids.len()).then_some(ordered)
}
