//! The loaders and sources `sqb load` runs for `--select` and `--exclude`.

use std::collections::BTreeSet;

use crate::load_command::_helpers::graph::GraphIndex;
use crate::load_command::_helpers::selection_sets::Selection;
use crate::load_command::constants::UPSTREAM_MARK;
use crate::load_command::errors::UnknownLoadSelector;
use crate::load_command::models::{LoadEntry, LoadGraph};

/// Intermediate loaders in dependency order, then selected sources in declaration order.
pub fn select_load_entries(
    graph: &LoadGraph,
    (select, exclude): (&[String], &[String]),
) -> Result<Vec<LoadEntry>, UnknownLoadSelector> {
    let index: GraphIndex = GraphIndex::new(graph);
    let selectors: Vec<String> = if select.is_empty() {
        index
            .source_order
            .iter()
            .map(|name| format!("{UPSTREAM_MARK}{name}"))
            .collect()
    } else {
        select.to_vec()
    };
    let mut selection: Selection = Selection::default();
    selection.select(&index, &selectors)?;
    selection.exclude(&index, exclude)?;
    selection.prune_missing_dependencies(&index);
    selection.prune_unneeded_loaders(&index);
    let terminal: BTreeSet<&String> = selection
        .sources
        .iter()
        .map(|source| &index.source_loader[source])
        .collect();
    let mut entries: Vec<LoadEntry> = index
        .topological_order(&selection.loaders)
        .into_iter()
        .filter(|loader| !terminal.contains(loader))
        .map(LoadEntry::Loader)
        .collect();
    entries.extend(
        index
            .source_order
            .iter()
            .filter(|name| selection.sources.contains(*name))
            .cloned()
            .map(LoadEntry::Source),
    );
    Ok(entries)
}
