//! Python's `validate_test_ctes` for model SQL tests.

use std::collections::HashSet;

use crate::test_targets::models::{TargetCatalog, TestTargets};

/// Python's error for the first unknown target in its validation order, or None.
#[must_use]
pub fn unknown_test_target(
    file_label: &str,
    catalog: &TargetCatalog,
    targets: &TestTargets,
) -> Option<String> {
    let groups: [(&str, &[String], &HashSet<String>); 7] = [
        ("mocks unknown model", &targets.mock_models, &catalog.models),
        (
            "mocks unknown source",
            &targets.mock_sources,
            &catalog.sources,
        ),
        ("mocks unknown seed", &targets.mock_seeds, &catalog.seeds),
        (
            "mocks unknown table function",
            &targets.mock_table_functions,
            &catalog.table_functions,
        ),
        ("mocks unknown macro", &targets.macro_mocks, &catalog.macros),
        (
            "expects unknown model",
            &targets.expected_models,
            &catalog.models,
        ),
        (
            "assertion references unknown model",
            &targets.assertion_targets,
            &catalog.models,
        ),
    ];
    for (phrase, names, known) in groups {
        if let Some(name) = names.iter().find(|name| !known.contains(name.as_str())) {
            return Some(format!("SQL test file {file_label} {phrase} '{name}'"));
        }
    }
    None
}
