//! Relation references test-authored SQL-test CTEs call, and which models they make a test run.

use crate::compiler::_helpers::sql_tests::helper_scope::read_helper_sql;
use crate::compiler::_helpers::sql_tests::markers::{ProtectedRanges, marker_names};
use crate::compiler::_helpers::sql_tests::planning::{SqlTestPatterns, TestFixtures};

/// Whether test-authored SQL calls a reference or function SQLBuild resolves for the test query.
pub(crate) fn calls_reference(sql: &str, patterns: &SqlTestPatterns) -> bool {
    patterns.test_reference.is_match(sql) || patterns.udf.is_match(sql)
}

/// The first relation reference call left outside comments and quoted text, as written.
pub(crate) fn unresolved_relation_call(sql: &str, patterns: &SqlTestPatterns) -> Option<String> {
    if !patterns.test_reference.is_match(sql) {
        return None;
    }
    let mut protected = ProtectedRanges::new(&patterns.lexical, sql);
    for pattern in [
        &patterns.reference,
        &patterns.source,
        &patterns.seed,
        &patterns.dbt_reference,
    ] {
        for found in pattern.find_iter(sql) {
            if !protected.contains(found.start()) {
                return Some(found.as_str().to_string());
            }
        }
    }
    None
}

/// The mock CTE that would stand in for one reference call, such as `__source__orders`.
pub(crate) fn mock_cte_example(call: &str) -> String {
    let names: Vec<&str> = call.split('"').skip(1).step_by(2).collect();
    let function = call
        .split('(')
        .next()
        .unwrap_or_default()
        .to_ascii_lowercase();
    format!("{function}__{}", names.join("__"))
}

/// Unmocked models the test's assertions, expected rows and the helpers they read call `__ref()` on.
pub(crate) fn reader_ref_targets(
    fixtures: &TestFixtures,
    patterns: &SqlTestPatterns,
) -> Vec<String> {
    let readers: Vec<&str> = fixtures
        .assertions
        .iter()
        .map(|(_, sql)| sql.as_str())
        .chain(fixtures.expected.values().map(String::as_str))
        .collect();
    let mut targets: Vec<String> = Vec::new();
    for sql in readers
        .iter()
        .copied()
        .chain(read_helper_sql(fixtures, &readers, patterns))
    {
        targets.extend(
            marker_names(&patterns.reference, &patterns.lexical, sql)
                .into_iter()
                .filter(|name| !fixtures.mock_refs.contains_key(name)),
        );
    }
    targets
}
