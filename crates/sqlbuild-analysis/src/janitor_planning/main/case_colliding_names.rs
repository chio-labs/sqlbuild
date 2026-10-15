//! Folded names shared by several relations in one listing.

use std::collections::{HashMap, HashSet};

/// Case-folded names that occur more than once in `names`.
pub fn case_colliding_names<'a>(names: impl IntoIterator<Item = &'a str>) -> HashSet<String> {
    let mut counts: HashMap<String, usize> = HashMap::new();
    for name in names {
        *counts.entry(name.to_lowercase()).or_insert(0) += 1;
    }
    counts
        .into_iter()
        .filter(|(_, count)| *count > 1)
        .map(|(name, _)| name)
        .collect()
}
