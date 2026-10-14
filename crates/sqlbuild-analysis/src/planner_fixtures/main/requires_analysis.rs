//! Select incomplete or open fixture schemas for read analysis.

use std::collections::BTreeSet;

use crate::planner_fixtures::models::FixtureColumn;

/// Require analysis unless every authoritative name is supplied.
pub fn requires_analysis(
    supplied: &[FixtureColumn],
    authoritative: Option<&BTreeSet<String>>,
) -> bool {
    authoritative.is_none_or(|expected| {
        let supplied_names: BTreeSet<_> =
            supplied.iter().map(|column| &column.folded_name).collect();
        expected.iter().any(|name| !supplied_names.contains(name))
    })
}
