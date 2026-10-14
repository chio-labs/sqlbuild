//! Breadth-first reachability and path nodes over combined graph edges.

use std::collections::{HashSet, VecDeque};

use crate::dbt_graph::models::{DbtGraphEdges, DbtGraphKey};

/// Every key reachable from `start`; `start` itself only through a cycle.
pub(crate) fn reachable(start: &DbtGraphKey, edges: &DbtGraphEdges) -> HashSet<DbtGraphKey> {
    let mut visited: HashSet<DbtGraphKey> = HashSet::new();
    let mut frontier: VecDeque<&DbtGraphKey> = VecDeque::from([start]);
    while let Some(current) = frontier.pop_front() {
        for neighbor in edges.targets.get(current).into_iter().flatten() {
            if visited.insert(neighbor.clone()) {
                frontier.push_back(neighbor);
            }
        }
    }
    visited
}

/// Keys on directed paths from `start` to `end`, or `None` when `end` is not downstream.
pub(crate) fn path_nodes(
    (start, end): (&DbtGraphKey, &DbtGraphKey),
    downstream: &DbtGraphEdges,
    upstream: &DbtGraphEdges,
) -> Option<HashSet<DbtGraphKey>> {
    let reachable_keys: HashSet<DbtGraphKey> = reachable(start, downstream);
    if !reachable_keys.contains(end) {
        return None;
    }
    let mut upstream_from_end: HashSet<DbtGraphKey> = HashSet::new();
    let mut stack: Vec<&DbtGraphKey> = vec![end];
    while let Some(current) = stack.pop() {
        if !upstream_from_end.insert(current.clone()) {
            continue;
        }
        for parent in upstream.targets.get(current).into_iter().flatten() {
            if reachable_keys.contains(parent) || parent == start {
                stack.push(parent);
            }
        }
    }
    let mut nodes: HashSet<DbtGraphKey> = reachable_keys
        .intersection(&upstream_from_end)
        .cloned()
        .collect();
    nodes.insert(start.clone());
    nodes.insert(end.clone());
    Some(nodes)
}
