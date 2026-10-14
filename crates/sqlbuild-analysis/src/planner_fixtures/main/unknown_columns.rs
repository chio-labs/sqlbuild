//! Diagnose supplied names outside a closed relation schema.

use std::collections::BTreeSet;

use crate::planner_fixtures::models::FixtureColumn;

/// Report sorted unknown names while preserving duplicate supplied names.
pub fn unknown_columns(
    label: &str,
    supplied: &[FixtureColumn],
    authoritative: Option<&BTreeSet<String>>,
) -> Option<String> {
    let expected = authoritative?;
    let mut unknown: Vec<_> = supplied
        .iter()
        .filter(|column| !expected.contains(&column.folded_name))
        .map(|column| column.name.as_str())
        .collect();
    unknown.sort_unstable();
    (!unknown.is_empty())
        .then(|| format!("{label} supplies unknown columns: {}", unknown.join(", ")))
}
