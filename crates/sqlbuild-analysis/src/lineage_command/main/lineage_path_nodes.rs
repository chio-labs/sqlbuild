//! Resources on directed paths between two endpoints.

use std::collections::HashSet;

use crate::lineage_command::_helpers::graph::{EdgeMap, closure, edge_map};
use crate::lineage_command::models::{LineageIndex, LineageKey};

/// Keys on downstream paths from `start` to `end`, or none when `end` is not downstream.
#[must_use]
pub fn lineage_path_nodes(
    index: &LineageIndex,
    start: &LineageKey,
    end: &LineageKey,
) -> Vec<LineageKey> {
    let downstream: EdgeMap<'_> = edge_map(&index.downstream);
    let reachable: HashSet<LineageKey> = closure(&downstream, std::slice::from_ref(start), None);
    if !reachable.contains(end) {
        return Vec::new();
    }
    let mut upstream_of_end: HashSet<&LineageKey> = HashSet::new();
    let mut stack: Vec<&LineageKey> = vec![end];
    while let Some(current) = stack.pop() {
        if !upstream_of_end.insert(current) {
            continue;
        }
        for (parent, children) in &index.downstream {
            if children.contains(current) && (reachable.contains(parent) || parent == start) {
                stack.push(parent);
            }
        }
    }
    let mut nodes: Vec<LineageKey> = reachable
        .iter()
        .filter(|key| upstream_of_end.contains(key))
        .cloned()
        .collect();
    nodes.push(start.clone());
    nodes.push(end.clone());
    nodes
}
