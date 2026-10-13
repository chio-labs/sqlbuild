//! Relation lineage around positional targets.

use std::collections::{HashMap, HashSet};

use crate::lineage_command::_helpers::graph::{build_graph, expand, sorted_keys};
use crate::lineage_command::_helpers::targets::unknown_lineage_target;
use crate::lineage_command::errors::LineageError;
use crate::lineage_command::models::{LineageGraph, LineageIndex, LineageKey};

/// The targets and every resource `direction` reaches from them within `depth`.
pub fn select_target_lineage(
    index: &LineageIndex,
    targets: &[String],
    (direction, depth): (&str, Option<i64>),
) -> Result<LineageGraph, LineageError> {
    let names: HashMap<&str, &LineageKey> = index
        .all_keys
        .iter()
        .map(|(name, key)| (name.as_str(), key))
        .collect();
    let mut keys: Vec<LineageKey> = Vec::new();
    for target in targets {
        let Some(key) = names.get(target.as_str()) else {
            return Err(unknown_lineage_target(target));
        };
        keys.push((*key).clone());
    }
    let mut selected: HashSet<LineageKey> = keys.iter().cloned().collect();
    selected.extend(expand(index, &keys, (direction, depth)));
    Ok(build_graph(
        index,
        &selected,
        (sorted_keys(&keys), Some(direction)),
    ))
}
