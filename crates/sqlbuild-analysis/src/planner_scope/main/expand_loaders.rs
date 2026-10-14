//! Expand validated loader DAGs without recursive traversal.

use crate::assembly::project::types::ObjectKey;
use crate::planner_scope::constants::SOURCE;
use crate::planner_scope::models::LoaderGraph;
use std::collections::{HashMap, HashSet};

/// Add loader dependency edges and executable upstream source keys in input iteration order.
pub fn expand_loaders(
    graph: &LoaderGraph,
    mut selected: Vec<ObjectKey>,
    mut upstream: Vec<(ObjectKey, Vec<ObjectKey>)>,
    executable: &HashSet<ObjectKey>,
) -> (Vec<ObjectKey>, Vec<(ObjectKey, Vec<ObjectKey>)>) {
    let mut positions: HashMap<ObjectKey, usize> = upstream
        .iter()
        .enumerate()
        .map(|(i, (k, _))| (k.clone(), i))
        .collect();
    let mut selected_seen: HashSet<ObjectKey> = selected.iter().cloned().collect();
    for key in selected.clone() {
        if key.0 != SOURCE {
            continue;
        }
        let Some(loader) = graph.source_loader(&key) else {
            if !graph.sources.iter().any(|(name, _)| name == &key.1)
                && graph.loaders.contains_key(&key.1)
                && !positions.contains_key(&key)
            {
                positions.insert(key.clone(), upstream.len());
                upstream.push((key, Vec::new()));
            }
            continue;
        };
        let Some(deps) = graph.loaders.get(loader) else {
            continue;
        };
        let mut pending = vec![(key.clone(), deps)];
        let mut visited: HashSet<ObjectKey> = HashSet::new();
        while let Some((node, dependencies)) = pending.pop() {
            if !visited.insert(node.clone()) {
                continue;
            }
            let edges: Vec<ObjectKey> = dependencies.iter().map(|name| graph.key(name)).collect();
            if let Some(index) = positions.get(&node) {
                upstream[*index].1 = edges;
            } else {
                positions.insert(node.clone(), upstream.len());
                upstream.push((node, edges));
            }
            for name in dependencies.iter().rev() {
                if let Some(next) = graph.loaders.get(name) {
                    pending.push((graph.key(name), next));
                }
            }
        }
        if executable.contains(&key) {
            for name in graph.upstream(deps) {
                let node = graph.key(&name);
                if selected_seen.insert(node.clone()) {
                    selected.push(node);
                }
            }
        }
    }
    (selected, upstream)
}
