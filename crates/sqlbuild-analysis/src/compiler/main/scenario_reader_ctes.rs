//! The helper and fixture CTEs one scenario query reads.

use crate::compiler::models::ScenarioHelperScope;

/// The CTEs `sql` reads, transitively and dependencies first; fixtures only with `fixtures`.
#[must_use]
pub fn scenario_reader_ctes(
    scope: &ScenarioHelperScope,
    sql: &str,
    fixtures: bool,
) -> Vec<(String, String)> {
    scope.graph.reader_ctes(sql, &scope.patterns, fixtures)
}
