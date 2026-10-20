//! `dict.fromkeys` over keys: the position of each key's first occurrence, in order.

use std::collections::HashSet;
use std::hash::Hash;

/// The positions of the first occurrence of each distinct key.
#[must_use]
pub(crate) fn distinct_positions<K: Hash + Eq>(keys: &[K]) -> Vec<usize> {
    let mut seen: HashSet<&K> = HashSet::with_capacity(keys.len());
    let mut positions: Vec<usize> = Vec::new();
    for (position, key) in keys.iter().enumerate() {
        if seen.insert(key) {
            positions.push(position);
        }
    }
    positions
}
