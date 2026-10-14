//! Intermediate source names required by selected loader nodes.

use crate::assembly::project::types::ObjectKey;
use crate::planner_scope::constants::SOURCE;
use crate::planner_scope::models::LoaderGraph;
use std::collections::HashSet;

/// Intermediate loader names in selected or upstream first-seen order.
pub fn intermediate_sources(
    graph: &LoaderGraph,
    selected: &[ObjectKey],
    upstream: bool,
) -> Vec<String> {
    let mut names: Vec<String> = Vec::new();
    let mut seen: HashSet<String> = HashSet::new();
    for key in selected {
        if key.0 != SOURCE {
            continue;
        }
        let candidates = if upstream {
            graph
                .source_loader(key)
                .and_then(|loader| graph.loaders.get(loader))
                .map(|deps| graph.upstream(deps))
                .unwrap_or_default()
        } else if !graph.sources.iter().any(|(name, _)| name == &key.1) {
            vec![key.1.clone()]
        } else {
            Vec::new()
        };
        for name in candidates {
            if graph.intermediate(&name) && seen.insert(name.clone()) {
                names.push(name);
            }
        }
    }
    names
}
