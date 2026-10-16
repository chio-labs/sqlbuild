//! Closures and selected-graph assembly over a lineage index.

use std::collections::{HashMap, HashSet};
use std::convert::Infallible;

use sqlbuild_core::graph_walk::main::breadth_first_reach::breadth_first_reach;

use crate::lineage_command::constants::{
    BOTH_DIRECTIONS, DOWNSTREAM_DIRECTION, UPSTREAM_DIRECTION,
};
use crate::lineage_command::models::{LineageGraph, LineageIndex, LineageKey, LineageNode};

/// Edge lists by key.
pub(crate) type EdgeMap<'a> = HashMap<&'a LineageKey, &'a [LineageKey]>;

/// `edges` as a lookup by key.
pub(crate) fn edge_map(edges: &[(LineageKey, Vec<LineageKey>)]) -> EdgeMap<'_> {
    edges
        .iter()
        .map(|(key, targets)| (key, targets.as_slice()))
        .collect()
}

/// Keys within `max_depth` edges of any start; a start is included only when reached again.
pub(crate) fn closure(
    edges: &EdgeMap<'_>,
    starts: &[LineageKey],
    max_depth: Option<i64>,
) -> HashSet<LineageKey> {
    let mut visited: HashSet<&LineageKey> = HashSet::new();
    let Ok(()) = breadth_first_reach(
        starts,
        max_depth.map(|maximum| u64::try_from(maximum).unwrap_or(0)),
        &mut visited,
        |current| Ok::<_, Infallible>(edges.get(*current).copied().unwrap_or_default()),
    );
    visited.into_iter().cloned().collect()
}

/// The keys `direction` reaches from `keys` within `depth`.
pub(crate) fn expand(
    index: &LineageIndex,
    keys: &[LineageKey],
    (direction, depth): (&str, Option<i64>),
) -> HashSet<LineageKey> {
    let mut expanded: HashSet<LineageKey> = HashSet::new();
    if direction == UPSTREAM_DIRECTION || direction == BOTH_DIRECTIONS {
        expanded.extend(closure(&edge_map(&index.upstream), keys, depth));
    }
    if direction == DOWNSTREAM_DIRECTION || direction == BOTH_DIRECTIONS {
        expanded.extend(closure(&edge_map(&index.downstream), keys, depth));
    }
    expanded
}

/// `keys` sorted by resource type, then name.
pub(crate) fn sorted_keys<'a>(keys: impl IntoIterator<Item = &'a LineageKey>) -> Vec<LineageKey> {
    let mut sorted: Vec<LineageKey> = keys.into_iter().cloned().collect();
    sorted.sort();
    sorted.dedup();
    sorted
}

/// Display nodes and the upstream edges between selected keys.
pub(crate) fn build_graph(
    index: &LineageIndex,
    selected: &HashSet<LineageKey>,
    (focus_keys, direction): (Vec<LineageKey>, Option<&str>),
) -> LineageGraph {
    let ordered: Vec<LineageKey> = sorted_keys(selected);
    let upstream: EdgeMap<'_> = edge_map(&index.upstream);
    let mut edges: Vec<(LineageKey, LineageKey)> = Vec::new();
    for downstream in &ordered {
        for upstream_key in upstream.get(downstream).copied().unwrap_or_default() {
            if selected.contains(upstream_key) {
                edges.push((upstream_key.clone(), downstream.clone()));
            }
        }
    }
    LineageGraph {
        nodes: ordered
            .iter()
            .map(|key| {
                index
                    .nodes
                    .get(key)
                    .cloned()
                    .unwrap_or_else(|| LineageNode {
                        key: key.clone(),
                        relative_path: None,
                        qualified_name: None,
                    })
            })
            .collect(),
        edges,
        focus_keys,
        direction: direction.map(str::to_owned),
    }
}
