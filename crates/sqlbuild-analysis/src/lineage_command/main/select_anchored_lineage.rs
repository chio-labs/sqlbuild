//! Selector lineage focused on its anchors, trimmed to `--depth` around them.

use std::collections::HashSet;

use crate::lineage_command::_helpers::graph::{build_graph, closure, edge_map, sorted_keys};
use crate::lineage_command::models::{LineageAnchors, LineageGraph, LineageIndex, LineageKey};

/// The selected keys, keeping only those within `depth` of an anchor when a depth is given.
pub fn select_anchored_lineage(
    index: &LineageIndex,
    selected: &[LineageKey],
    (anchors, depth): (&LineageAnchors, Option<i64>),
) -> LineageGraph {
    let mut keys: HashSet<LineageKey> = selected.iter().cloned().collect();
    if let Some(depth) = depth {
        let mut retained: HashSet<LineageKey> = anchors.retained.iter().cloned().collect();
        retained.extend(anchors.upstream.iter().cloned());
        retained.extend(anchors.downstream.iter().cloned());
        retained.extend(closure(
            &edge_map(&index.upstream),
            &anchors.upstream,
            Some(depth),
        ));
        retained.extend(closure(
            &edge_map(&index.downstream),
            &anchors.downstream,
            Some(depth),
        ));
        keys.retain(|key| retained.contains(key));
    }
    let focus: Vec<LineageKey> = sorted_keys(anchors.upstream.iter().chain(&anchors.downstream));
    build_graph(index, &keys, (focus, None))
}
