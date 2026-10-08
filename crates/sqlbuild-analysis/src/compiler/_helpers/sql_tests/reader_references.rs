//! Relation references test-authored SQL-test CTEs call, and which of them a test can resolve.

use serde_json::json;

use crate::compiler::_helpers::sql_tests::markers::{ProtectedRanges, marker_names};
use crate::compiler::_helpers::sql_tests::planning::{
    SqlTestPatterns, TestFixtures, planner_error,
};

/// Prefix of the planner error for a reference a test CTE calls that the test cannot resolve.
pub(crate) const UNRESOLVED_REFERENCE_ERROR_PREFIX: &str = "sql_test_reference:";

/// Whether test-authored SQL calls a reference or function SQLBuild resolves for the test query.
pub(crate) fn calls_reference(sql: &str, patterns: &SqlTestPatterns) -> bool {
    patterns.test_reference.is_match(sql) || patterns.udf.is_match(sql)
}

/// Unmocked models the test's assertions call `__ref()` on.
pub(crate) fn assertion_ref_targets(
    fixtures: &TestFixtures,
    patterns: &SqlTestPatterns,
) -> Vec<String> {
    let mut targets: Vec<String> = Vec::new();
    for (_, sql) in &fixtures.assertions {
        targets.extend(
            marker_names(&patterns.reference, &patterns.lexical, sql)
                .into_iter()
                .filter(|name| !fixtures.mock_refs.contains_key(name)),
        );
    }
    targets
}

/// The first relation reference call, outside comments and quoted text, that neither a mock nor a model the test runs resolves.
pub(crate) fn unresolvable_call(
    sql: &str,
    fixtures: &TestFixtures,
    chain: &[String],
    patterns: &SqlTestPatterns,
) -> Option<String> {
    if !patterns.test_reference.is_match(sql) {
        return None;
    }
    let mut protected = ProtectedRanges::new(&patterns.lexical, sql);
    let groups = [
        (&patterns.reference, &fixtures.mock_refs, true),
        (&patterns.source, &fixtures.mock_sources, false),
        (&patterns.seed, &fixtures.mock_seeds, false),
        (&patterns.dbt_reference, &fixtures.mock_dbt_refs, false),
    ];
    for (pattern, mocks, runs_models) in groups {
        for captures in pattern.captures_iter(sql) {
            let Some(full) = captures.get(0) else {
                continue;
            };
            if protected.contains(full.start()) {
                continue;
            }
            let name = match (captures.get(1), captures.get(2)) {
                (Some(first), Some(second)) => format!("{}__{}", first.as_str(), second.as_str()),
                (Some(first), None) => first.as_str().to_string(),
                _ => continue,
            };
            let runs = runs_models && chain.contains(&name);
            if !runs && !mocks.contains_key(&name) {
                return Some(full.as_str().to_string());
            }
        }
    }
    None
}

/// The planner error for a reference call one test CTE makes that the test cannot resolve.
pub(crate) fn unresolved_reference_error(
    test_name: &str,
    file_label: &str,
    cte_name: &str,
    call: &str,
) -> String {
    let payload = json!({
        "testName": test_name,
        "fileLabel": file_label,
        "cteName": cte_name,
        "call": call,
        "mockCte": mock_cte_example(call),
    });
    format!("{UNRESOLVED_REFERENCE_ERROR_PREFIX}{payload}")
}

/// The mock CTE that would stand in for one reference call, such as `__source__orders`.
fn mock_cte_example(call: &str) -> String {
    let names: Vec<&str> = call.split('"').skip(1).step_by(2).collect();
    let function = call
        .split('(')
        .next()
        .unwrap_or_default()
        .to_ascii_lowercase();
    format!("{function}__{}", names.join("__"))
}

/// Which helpers a test reads and which models its test CTEs make it run, as the compiler found.
pub(crate) struct CompilerReads {
    pub(crate) read_helper_names: Vec<String>,
    pub(crate) reference_target_model_names: Vec<String>,
}

impl CompilerReads {
    /// Require the compiler's reads; planning without them could leave references raw.
    pub(crate) fn required(
        file_label: &str,
        read_helper_names: Option<Vec<String>>,
        reference_target_model_names: Option<Vec<String>>,
    ) -> Result<Self, String> {
        match (read_helper_names, reference_target_model_names) {
            (Some(read_helper_names), Some(reference_target_model_names)) => Ok(Self {
                read_helper_names,
                reference_target_model_names,
            }),
            _ => Err(planner_error(&format!(
                "SQL test '{file_label}' planning request omits readHelperNames or \
                 referenceTargetModelNames, which the compiler computes for every model test"
            ))),
        }
    }
}
