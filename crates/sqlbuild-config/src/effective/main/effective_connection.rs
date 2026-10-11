//! `build_effective_connection`: the project connection with every override, before expansion.

use std::hash::Hash;

use crate::effective::_helpers::entries::{lookup, updated};
use crate::effective::errors::EffectiveConfigError;
use crate::effective::models::ConnectionLayers;
use crate::effective::types::Entries;

/// The merged connection, or the unknown connection a target selects.
pub fn effective_connection<K: Eq + Hash + Clone, V: Clone>(
    layers: ConnectionLayers<K, V>,
) -> Result<Entries<K, V>, EffectiveConfigError<K>> {
    let mut connection: Entries<K, V> = layers.project;
    if let Some((name, target)) = layers.target {
        if let Some(name) = name {
            let project = lookup(&layers.project_named, &name);
            let local = lookup(&layers.local_named, &name);
            if project.is_none() && local.is_none() {
                return Err(EffectiveConfigError::UnknownConnection(name));
            }
            connection = updated(connection, project.map(Vec::as_slice).unwrap_or_default());
            connection = updated(connection, local.map(Vec::as_slice).unwrap_or_default());
        }
        connection = updated(connection, &target);
    }
    Ok(updated(connection, &layers.local))
}
