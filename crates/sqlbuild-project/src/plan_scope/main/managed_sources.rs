//! Direct managed sources required by selected models.

use crate::plan_scope::constants::{MODEL, SOURCE};
use sqlbuild_analysis::assembly::project::types::ObjectKey;
use std::collections::HashSet;

/// Select only direct managed source dependencies of selected models.
pub fn managed_sources(
    selected: &[ObjectKey],
    upstream: &[(ObjectKey, Vec<ObjectKey>)],
    managed: &HashSet<String>,
) -> HashSet<ObjectKey> {
    let selected: HashSet<&ObjectKey> = selected.iter().filter(|key| key.0 == MODEL).collect();
    upstream
        .iter()
        .filter(|(key, _)| selected.contains(key))
        .flat_map(|(_, deps)| deps)
        .filter(|key| key.0 == SOURCE && managed.contains(&key.1))
        .cloned()
        .collect()
}
