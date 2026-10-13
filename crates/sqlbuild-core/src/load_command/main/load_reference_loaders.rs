//! Unselected upstream loaders that selected loads only reference.

use std::collections::BTreeSet;

use crate::load_command::_helpers::graph::GraphIndex;
use crate::load_command::models::LoadGraph;

/// Loaders upstream of the selected entries' loaders, in dependency order, minus selected names.
#[must_use]
pub fn load_reference_loaders(
    graph: &LoadGraph,
    selected: &[(String, Option<String>)],
) -> Vec<String> {
    let index: GraphIndex = GraphIndex::new(graph);
    let mut references: BTreeSet<String> = BTreeSet::new();
    for (_, loader) in selected {
        let Some(loader) = loader else { continue };
        for dependency in index.dependencies(loader) {
            references.extend(index.upstream_closure(dependency));
        }
    }
    let selected_names: BTreeSet<&String> = selected.iter().map(|(name, _)| name).collect();
    index
        .topological_order(&references)
        .into_iter()
        .filter(|loader| index.is_loader(loader) && !selected_names.contains(loader))
        .collect()
}
