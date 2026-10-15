//! Header key sets as the sorted lists native discovery options take.

/// A header key set as owned keys, sorted by code point as Python sorts them.
pub(crate) fn sorted_keys(keys: &[&str]) -> Vec<String> {
    let mut keys: Vec<String> = keys.iter().map(|key| (*key).to_owned()).collect();
    keys.sort();
    keys
}
