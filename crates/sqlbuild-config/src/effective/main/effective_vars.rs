//! `build_effective_vars`: project, target, local, then CLI vars, before template expansion.

use std::hash::Hash;

use crate::effective::_helpers::entries::updated;
use crate::effective::types::Entries;

/// The vars of every layer merged, lowest precedence first, with `dict.update` semantics.
#[must_use]
pub fn effective_vars<K: Eq + Hash + Clone, V: Clone>(layers: &[&[(K, V)]]) -> Entries<K, V> {
    layers
        .iter()
        .fold(Vec::new(), |vars, layer| updated(vars, layer))
}
