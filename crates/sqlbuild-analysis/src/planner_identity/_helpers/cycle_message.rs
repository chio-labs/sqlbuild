//! The dependency-cycle message naming the keys left unordered and the injected edges between them.

use std::collections::{BTreeSet, HashMap, HashSet};

use crate::planner_identity::models::GraphKey;

/// Upstream edges and the origins of injected edges.
type CycleEdges<'a> = (
    &'a [(GraphKey, Vec<GraphKey>)],
    &'a HashMap<(GraphKey, GraphKey), String>,
);

/// The message for the keys Kahn's algorithm could not order.
pub(crate) fn cycle_message(
    ordered: &[GraphKey],
    node_keys: HashSet<&GraphKey>,
    (upstream, injected_edge_origins): CycleEdges<'_>,
) -> String {
    let ordered_set: HashSet<&GraphKey> = ordered.iter().collect();
    let mut cycle_keys: Vec<&GraphKey> = node_keys
        .into_iter()
        .filter(|key| !ordered_set.contains(key))
        .collect();
    cycle_keys.sort();
    let names: Vec<String> = cycle_keys
        .iter()
        .map(|key| format!("{}:{}", key.kind, key.name))
        .collect();
    format!(
        "Dependency cycle detected involving: {}{}",
        names.join(", "),
        cycle_origin_notes(&cycle_keys, upstream, injected_edge_origins)
    )
}

fn cycle_origin_notes(
    cycle_keys: &[&GraphKey],
    upstream: &[(GraphKey, Vec<GraphKey>)],
    injected_edge_origins: &HashMap<(GraphKey, GraphKey), String>,
) -> String {
    if injected_edge_origins.is_empty() {
        return String::new();
    }
    let cycle_set: HashSet<&GraphKey> = cycle_keys.iter().copied().collect();
    let deps: HashMap<&GraphKey, &Vec<GraphKey>> =
        upstream.iter().map(|(key, deps)| (key, deps)).collect();
    let mut notes: BTreeSet<&str> = BTreeSet::new();
    for key in cycle_keys {
        for dep_key in deps.get(key).into_iter().flat_map(|deps| deps.iter()) {
            if !cycle_set.contains(dep_key) {
                continue;
            }
            if let Some(origin) = injected_edge_origins.get(&((*key).clone(), dep_key.clone())) {
                notes.insert(origin);
            }
        }
    }
    if notes.is_empty() {
        return String::new();
    }
    format!(
        " (via {})",
        notes.into_iter().collect::<Vec<&str>>().join("; ")
    )
}
