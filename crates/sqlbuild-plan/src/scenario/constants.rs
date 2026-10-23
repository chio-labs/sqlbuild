//! Exact authored scenario marker grammar.

pub(super) const MARKERS: [&str; 4] = ["__ref(", "__seed(", "__source(", "__dbt_ref("];
pub(super) const DBT_REF_MARKER: usize = 3;
pub(super) const HASH_LENGTH: usize = 12;
/// Missing sources named in full before the rest are counted.
pub(super) const LISTED_MISSING_SOURCES: usize = 5;
