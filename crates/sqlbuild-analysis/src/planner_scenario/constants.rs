//! Exact authored scenario marker grammar.

pub(super) const MARKERS: [&str; 4] = ["__ref(", "__seed(", "__source(", "__dbt_ref("];
pub(super) const DBT_REF_MARKER: usize = 3;
pub(super) const HASH_LENGTH: usize = 12;
