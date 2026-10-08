//! Python's `_validate_scenario_source_references`.

use std::collections::HashSet;

use crate::test_targets::models::ScenarioCteSources;

/// Python's error for the first source a scenario may not read; check CTEs are read first.
#[must_use]
pub fn scenario_source_violation(
    file_label: &str,
    ctes: &[ScenarioCteSources],
    known_sources: &HashSet<String>,
) -> Option<String> {
    for cte in ctes.iter().filter(|cte| cte.check) {
        if let Some(source) = cte.sources.first() {
            return Some(format!(
                "SQL scenario file {file_label} CTE '{}' must not reference project source \
                 '{source}' with __source(); source-backed scenario data is only allowed \
                 in helper and fixture CTEs",
                cte.name
            ));
        }
    }
    for cte in ctes.iter().filter(|cte| !cte.check) {
        if let Some(source) = cte
            .sources
            .iter()
            .find(|source| !known_sources.contains(source.as_str()))
        {
            return Some(format!(
                "SQL scenario file {file_label} references unknown source '{source}'"
            ));
        }
    }
    None
}
