//! `dbt_bool_text`: the boolean dbt's `as_bool` reads from text.

use sqlbuild_core::text::main::python_strip::python_strip;

use crate::dbt_profile::constants::{DBT_FALSE_VALUES, DBT_TRUE_VALUES};

/// The boolean dbt's `as_bool` reads from stripped, lowercased text, or `None`.
#[must_use]
pub fn dbt_bool_text(text: &str) -> Option<bool> {
    let normalized: String = python_strip(text).to_lowercase();
    if DBT_TRUE_VALUES.contains(&normalized.as_str()) {
        return Some(true);
    }
    DBT_FALSE_VALUES
        .contains(&normalized.as_str())
        .then_some(false)
}
