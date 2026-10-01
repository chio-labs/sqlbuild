use std::time::Instant;

use serde_json::{Value, json};

use crate::sql_lint::main::engine::lint_json;
use crate::sql_quality::tests::helpers::wide_cte_chain;
use crate::sql_quality::tests::test_types::QualityScaleTestCase;

#[test]
fn given_many_wide_ctes_with_findings_when_linting_then_quality_rules_stay_linear()
-> Result<(), String> {
    let test_cases = [QualityScaleTestCase {
        description: "1,500 wide CTEs, each dropping a column and ranking without a key",
        cte_count: 1_500,
        column_count: 24,
        expected_findings: 2_998,
        expected_max_seconds: 20.0,
    }];
    for test_case in &test_cases {
        let request: Value = json!({
            "version": 1,
            "sql": wide_cte_chain(test_case.cte_count, test_case.column_count),
            "dialect": "duckdb",
            "enabled_rules": ["SQBRSQL018", "SQBRSQL042", "SQBRSQL043", "SQBRSQL044"],
        });
        let started: Instant = Instant::now();
        let response: Value = serde_json::from_str(&lint_json(&request.to_string())?)
            .map_err(|error| error.to_string())?;
        let elapsed: f64 = started.elapsed().as_secs_f64();
        assert_eq!(
            response["diagnostics"].as_array().map_or(0, Vec::len),
            test_case.expected_findings,
            "{}",
            test_case.description
        );
        assert!(
            elapsed <= test_case.expected_max_seconds,
            "{}: {elapsed:.2}s",
            test_case.description
        );
    }
    Ok(())
}
