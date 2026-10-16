use std::collections::HashSet;

/// The keys of `keys` seen more than once, in first-repeat order.
pub(super) fn duplicates(keys: &[&'static str]) -> Vec<&'static str> {
    let mut seen: HashSet<&str> = HashSet::new();
    keys.iter()
        .copied()
        .filter(|key| !seen.insert(key))
        .collect()
}
