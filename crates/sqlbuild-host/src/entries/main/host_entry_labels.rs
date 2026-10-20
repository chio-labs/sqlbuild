//! Every host entry as `_native.HOST_ENTRIES` lists it.

use crate::entries::constants::HOST_ENTRIES;

/// Each entry's `(name, kind, edge)` labels, in `HOST_ENTRIES` order.
#[must_use]
pub fn host_entry_labels() -> Vec<(&'static str, &'static str, &'static str)> {
    HOST_ENTRIES
        .iter()
        .flat_map(|group| group.iter())
        .map(|entry| (entry.name, entry.kind.label(), entry.edge.label()))
        .collect()
}
