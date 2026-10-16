//! Resources on directed paths between two endpoints.

use std::collections::HashSet;

use sqlbuild_core::graph_walk::main::directed_path_nodes::directed_path_nodes;

use crate::lineage_command::_helpers::graph::{EdgeMap, edge_map};
use crate::lineage_command::models::{LineageIndex, LineageKey};

/// Keys on downstream paths from `start` to `end`, or none when `end` is not downstream.
#[must_use]
pub fn lineage_path_nodes(
    index: &LineageIndex,
    start: &LineageKey,
    end: &LineageKey,
) -> Vec<LineageKey> {
    let downstream: EdgeMap<'_> = edge_map(&index.downstream);
    let (mut reachable, mut path): (HashSet<&LineageKey>, HashSet<&LineageKey>) =
        (HashSet::new(), HashSet::new());
    let Ok(found) = directed_path_nodes(
        (start, end),
        (
            |current: &&LineageKey| Ok(downstream.get(*current).copied().unwrap_or_default()),
            |current: &&LineageKey| {
                Ok(index
                    .downstream
                    .iter()
                    .filter(|(_, children)| children.contains(*current))
                    .map(|(parent, _)| parent)
                    .collect::<Vec<&LineageKey>>())
            },
        ),
        (&mut reachable, &mut path),
    );
    if !found {
        return Vec::new();
    }
    path.into_iter().cloned().collect()
}
