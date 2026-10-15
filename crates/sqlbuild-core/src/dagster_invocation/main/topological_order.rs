//! DAG node order for emitting Dagster events.

use std::collections::{BTreeSet, HashMap, VecDeque};

use crate::dagster_invocation::_helpers::graph::{
    EdgeSets, edge_sets, id_positions, initially_ready, unique_positions,
};

/// Node positions in Kahn order over known edges, or `None` when a cycle leaves nodes out.
#[must_use]
pub fn topological_order(ids: &[String], edges: &[(String, String)]) -> Option<Vec<usize>> {
    let positions: HashMap<&str, usize> = id_positions(ids);
    let unique: Vec<usize> = unique_positions(ids, &positions);
    let EdgeSets {
        mut incoming,
        outgoing,
    } = edge_sets(&unique, (&positions, edges));
    let mut ready: VecDeque<usize> = initially_ready(&unique, &incoming);
    let mut ordered: Vec<usize> = Vec::new();
    while let Some(position) = ready.pop_front() {
        ordered.push(position);
        for downstream in outgoing.get(&position).cloned().unwrap_or_default() {
            let waiting: &mut BTreeSet<usize> = incoming.entry(downstream).or_default();
            waiting.remove(&position);
            if waiting.is_empty() {
                ready.push_back(downstream);
            }
        }
    }
    (ordered.len() == ids.len()).then_some(ordered)
}
