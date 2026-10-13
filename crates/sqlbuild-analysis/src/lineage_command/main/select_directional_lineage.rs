//! Selector lineage expanded by an explicit `--direction`.

use std::collections::HashSet;

use crate::lineage_command::_helpers::graph::{build_graph, expand, sorted_keys};
use crate::lineage_command::models::{LineageGraph, LineageIndex, LineageKey};

/// Selected keys plus what `direction` reaches within `depth`, minus the excluded keys.
pub fn select_directional_lineage(
    index: &LineageIndex,
    (selected, excluded): (&[LineageKey], &[LineageKey]),
    (direction, depth): (&str, Option<i64>),
) -> LineageGraph {
    let excluded: HashSet<&LineageKey> = excluded.iter().collect();
    let mut keys: HashSet<LineageKey> = selected.iter().cloned().collect();
    keys.extend(expand(index, selected, (direction, depth)));
    keys.retain(|key| !excluded.contains(key));
    let focus: Vec<LineageKey> = sorted_keys(selected.iter().filter(|key| !excluded.contains(key)));
    build_graph(index, &keys, (focus, Some(direction)))
}
