//! Python's compile-report execution layer count over the model subgraph.

use std::collections::{HashMap, HashSet};

use crate::assembly::project::types::ObjectKey;
use crate::graph::constants::MODEL_RESOURCE;
use crate::graph::models::{EdgeDirection, ProjectGraph};

/// Layers of a breadth-first topological walk over models; a cycle still counts at least one.
pub(crate) fn model_layer_count(graph: &ProjectGraph) -> usize {
    let models: HashSet<&ObjectKey> = graph
        .upstream
        .iter()
        .map(|(key, _)| key)
        .filter(|key| key.0 == MODEL_RESOURCE)
        .collect();
    if models.is_empty() {
        return 0;
    }
    let mut remaining: HashMap<&ObjectKey, HashSet<&ObjectKey>> = models
        .iter()
        .map(|&key| {
            (
                key,
                model_edges(graph, &models, key, EdgeDirection::Upstream),
            )
        })
        .collect();
    let mut layer: HashSet<&ObjectKey> = remaining
        .iter()
        .filter(|(_, deps)| deps.is_empty())
        .map(|(&key, _)| key)
        .collect();
    let mut visited: HashSet<&ObjectKey> = HashSet::new();
    let mut layers: usize = 0;
    while !layer.is_empty() {
        layers += 1;
        let mut next: HashSet<&ObjectKey> = HashSet::new();
        for key in layer {
            visited.insert(key);
            for downstream in model_edges(graph, &models, key, EdgeDirection::Downstream) {
                if visited.contains(downstream) {
                    continue;
                }
                if let Some(deps) = remaining.get_mut(downstream) {
                    deps.remove(key);
                    if deps.is_empty() {
                        next.insert(downstream);
                    }
                }
            }
        }
        layer = next;
    }
    if visited.len() == models.len() {
        layers
    } else {
        layers.max(1)
    }
}

fn model_edges<'graph>(
    graph: &'graph ProjectGraph,
    models: &HashSet<&ObjectKey>,
    key: &ObjectKey,
    direction: EdgeDirection,
) -> HashSet<&'graph ObjectKey> {
    graph
        .edges(key, direction)
        .iter()
        .filter(|dependency| models.contains(dependency))
        .collect()
}
