//! `_apply_default_connection`: a target without a connection uses the only named one.

use std::collections::BTreeSet;

use crate::effective::errors::EffectiveConfigError;
use crate::effective::models::ConnectionChoice;

/// The only named connection a target defaults to, `None` when it keeps its own, or ambiguity.
pub fn default_connection_name<K: Ord + Clone>(
    choice: ConnectionChoice<K>,
) -> Result<Option<K>, EffectiveConfigError<K>> {
    if choice.selected {
        return Ok(None);
    }
    let names: BTreeSet<K> = choice
        .project_names
        .into_iter()
        .chain(choice.local_names)
        .collect();
    let mut names: Vec<K> = names.into_iter().collect();
    match names.len() {
        0 => Ok(None),
        1 => Ok(names.pop()),
        _ => Err(EffectiveConfigError::AmbiguousConnection {
            target: choice.target,
            names,
        }),
    }
}
