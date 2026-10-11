//! Python `dict.update` over ordered entries.

use std::collections::HashMap;
use std::hash::Hash;

use crate::effective::types::Entries;

/// `into.update(from)`: existing keys keep their position and take the new value.
pub(crate) fn updated<K: Eq + Hash + Clone, V: Clone>(
    into: Entries<K, V>,
    from: &[(K, V)],
) -> Entries<K, V> {
    let mut entries: Entries<K, V> = into;
    let mut positions: HashMap<K, usize> = entries
        .iter()
        .enumerate()
        .map(|(position, (key, _))| (key.clone(), position))
        .collect();
    for (key, value) in from {
        match positions.get(key) {
            Some(position) => entries[*position].1 = value.clone(),
            None => {
                positions.insert(key.clone(), entries.len());
                entries.push((key.clone(), value.clone()));
            }
        }
    }
    entries
}

/// `mapping.get(key)`.
pub(crate) fn lookup<'a, K: Eq, V>(entries: &'a [(K, V)], key: &K) -> Option<&'a V> {
    entries
        .iter()
        .find(|(candidate, _)| candidate == key)
        .map(|(_, value)| value)
}
