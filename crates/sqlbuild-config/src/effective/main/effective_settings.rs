//! `build_effective_settings`: project settings with the local settings a file overrides.

use std::hash::Hash;

use crate::effective::_helpers::entries::{lookup, updated};
use crate::effective::types::Entries;

/// The local value of one overridden setting.
fn local_setting<K: Eq + Clone, V: Clone>(local: &[(K, V)], name: &K) -> Option<(K, V)> {
    lookup(local, name).map(|value| (name.clone(), value.clone()))
}

/// The project settings, each overridden name taking the local value.
#[must_use]
pub fn effective_settings<K: Eq + Hash + Clone, V: Clone>(
    project: Entries<K, V>,
    local: &[(K, V)],
    overrides: &[K],
) -> Entries<K, V> {
    let overridden: Entries<K, V> = overrides
        .iter()
        .filter_map(|name| local_setting(local, name))
        .collect();
    updated(project, &overridden)
}
