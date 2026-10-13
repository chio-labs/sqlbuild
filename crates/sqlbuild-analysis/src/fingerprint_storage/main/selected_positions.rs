//! In-memory node selection over unfiltered latest rows.

use std::collections::HashSet;

use crate::fingerprint_storage::models::FingerprintIdentity;

/// Positions of the rows a narrowed latest read would have returned.
pub fn selected_positions(
    identities: &[FingerprintIdentity<'_>],
    node_names: &[String],
    filtered_node_types: &[String],
) -> Vec<usize> {
    let names: HashSet<&str> = node_names.iter().map(String::as_str).collect();
    let types: HashSet<&str> = filtered_node_types.iter().map(String::as_str).collect();
    identities
        .iter()
        .enumerate()
        .filter(|(_, identity)| {
            names.contains(identity.node_name)
                || (!types.is_empty() && !types.contains(identity.node_type))
        })
        .map(|(position, _)| position)
        .collect()
}
