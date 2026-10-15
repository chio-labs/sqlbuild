//! `readable_columns`: the known columns a stored state table has, in their declared order.

use std::collections::HashSet;

/// The `known` columns present in `stored` (compared case-insensitively); later additions may be absent.
#[must_use]
pub fn readable_columns<'a>(known: &[&'a str], stored: &[String]) -> Vec<&'a str> {
    let stored: HashSet<String> = stored.iter().map(|column| column.to_lowercase()).collect();
    known
        .iter()
        .copied()
        .filter(|column| stored.contains(*column))
        .collect()
}
