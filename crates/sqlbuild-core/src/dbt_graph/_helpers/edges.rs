//! Insertion-ordered edge maps: adding nodes and edges, sorting and inversion.

use crate::dbt_graph::models::{DbtGraphEdges, DbtGraphKey};

/// `edges` with `key` added with no targets unless it is already present.
pub(crate) fn ensure(mut edges: DbtGraphEdges, key: &DbtGraphKey) -> DbtGraphEdges {
    if !edges.targets.contains_key(key) {
        edges.order.push(key.clone());
        edges.targets.insert(key.clone(), Vec::new());
    }
    edges
}

/// `edges` with one edge appended from `source`, adding `source` first when it is new.
pub(crate) fn push(
    edges: DbtGraphEdges,
    source: &DbtGraphKey,
    target: DbtGraphKey,
) -> DbtGraphEdges {
    let mut edges: DbtGraphEdges = ensure(edges, source);
    if let Some(targets) = edges.targets.get_mut(source) {
        targets.push(target);
    }
    edges
}

/// `edges` with every target list sorted by stable ID, duplicates kept.
pub(crate) fn sort_targets(mut edges: DbtGraphEdges) -> DbtGraphEdges {
    for targets in edges.targets.values_mut() {
        targets.sort_by_cached_key(DbtGraphKey::stable_id);
    }
    edges
}

/// Reversed edges: every source first, then each new target in first-seen order.
pub(crate) fn inverted(edges: &DbtGraphEdges) -> DbtGraphEdges {
    let mut result: DbtGraphEdges = DbtGraphEdges::default();
    for key in &edges.order {
        result = ensure(result, key);
    }
    for source in &edges.order {
        for target in edges.targets.get(source).into_iter().flatten() {
            result = push(result, target, source.clone());
        }
    }
    result
}
