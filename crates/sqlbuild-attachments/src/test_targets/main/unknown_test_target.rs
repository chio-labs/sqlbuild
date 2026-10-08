//! Python's `validate_test_ctes` for model SQL tests.

use std::collections::HashSet;

use crate::test_targets::models::TargetGroup;

/// Python's error for the first unknown target in group order, or None when all are known.
#[must_use]
pub fn unknown_test_target(file_label: &str, groups: &[TargetGroup]) -> Option<String> {
    for group in groups {
        let known: HashSet<&str> = group.known.iter().map(String::as_str).collect();
        if let Some(name) = group
            .names
            .iter()
            .find(|name| !known.contains(name.as_str()))
        {
            return Some(format!(
                "SQL test file {file_label} {} '{name}'",
                group.phrase
            ));
        }
    }
    None
}
