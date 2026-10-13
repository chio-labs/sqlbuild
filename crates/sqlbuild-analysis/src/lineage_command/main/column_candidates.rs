//! The models a column trace must analyse.

use std::collections::HashSet;

use crate::lineage_command::_helpers::graph::{EdgeMap, closure, edge_map};
use crate::lineage_command::constants::{DOWNSTREAM_DIRECTION, MODEL_RESOURCE_TYPE};
use crate::lineage_command::models::{ColumnCandidates, LineageIndex, LineageKey};

/// Models within `depth` of `key` in `direction`, and whether one more step reaches further.
#[must_use]
pub fn column_candidates(
    index: &LineageIndex,
    key: &LineageKey,
    (direction, depth): (&str, Option<i64>),
) -> ColumnCandidates {
    let edges: EdgeMap<'_> = edge_map(if direction == DOWNSTREAM_DIRECTION {
        &index.downstream
    } else {
        &index.upstream
    });
    let starts: &[LineageKey] = std::slice::from_ref(key);
    let mut selected: HashSet<LineageKey> = closure(&edges, starts, depth);
    selected.insert(key.clone());
    let mut model_names: Vec<String> = selected
        .iter()
        .filter(|selected| selected.resource_type == MODEL_RESOURCE_TYPE)
        .map(|selected| selected.name.clone())
        .collect();
    model_names.sort();
    model_names.dedup();
    let truncated: bool = depth.is_some_and(|depth| {
        let mut extended: HashSet<LineageKey> = closure(&edges, starts, Some(depth + 1));
        extended.insert(key.clone());
        extended != selected
    });
    ColumnCandidates {
        model_names,
        truncated,
    }
}
