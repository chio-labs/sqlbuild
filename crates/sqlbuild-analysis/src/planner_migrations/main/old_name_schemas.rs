//! Select old-name state schemas without repeating known-empty inspection.

use std::collections::BTreeSet;

/// Keep known state schemas and schemas absent from an available catalog listing.
pub fn old_name_schemas(
    needed: &BTreeSet<String>,
    state: &BTreeSet<String>,
    listed: Option<&BTreeSet<String>>,
) -> BTreeSet<String> {
    needed
        .iter()
        .filter(|schema| {
            let key = schema.to_lowercase();
            state.contains(&key) || listed.is_some_and(|listed| !listed.contains(&key))
        })
        .cloned()
        .collect()
}
