use serde_json::{Value, json};
use tempfile::TempDir;

use crate::engine::main::evaluate::evaluate_json;
use crate::engine::tests::helpers;
use crate::engine::tests::test_types;

#[test]
fn given_repeated_native_evaluation_when_faulting_then_returns_deterministic_complete_facts()
-> Result<(), String> {
    let test_cases = [test_types::NativeEvaluationTestCase {
        description: "repeated native evaluation preserves every fault fact",
        config: json!({
            "select": ["SQBKS001"],
            "cache": {"enabled": false, "require_cacheable": false}
        }),
        expected_faults: json!([{
            "code": "SQBKS001",
            "path": "models/mart/market__mart__prices.sql",
            "line": 1,
            "column": 1,
            "message": "model SQL must keep transformation logic in top-level CTEs",
            "remediation": "Move transformation logic into named top-level CTEs before the terminal SELECT."
        }]),
    }];

    for test_case in &test_cases {
        let project_dir = TempDir::new().map_err(|error| error.to_string())?;
        let request_json = helpers::request(&project_dir, &test_case.config);
        let first: Value = serde_json::from_str(&evaluate_json(&request_json)?)
            .map_err(|error| error.to_string())?;
        let second: Value = serde_json::from_str(&evaluate_json(&request_json)?)
            .map_err(|error| error.to_string())?;

        assert_eq!(
            first["faults"], second["faults"],
            "{}",
            test_case.description
        );
        assert_eq!(
            first["faults"], test_case.expected_faults,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_scoped_suppression_when_evaluating_native_fault_then_returns_no_faults()
-> Result<(), String> {
    let test_cases = [test_types::NativeEvaluationTestCase {
        description: "native evaluation applies a matching scoped suppression",
        config: json!({
            "select": ["SQBKS001"],
            "cache": {"enabled": false, "require_cacheable": false},
            "rule_ignores": [{
                "rules": ["SQBKS"],
                "paths": ["models/mart/**"],
                "reason": "Tracked migration"
            }]
        }),
        expected_faults: json!([]),
    }];

    for test_case in &test_cases {
        let project_dir = TempDir::new().map_err(|error| error.to_string())?;
        let request_json = helpers::request(&project_dir, &test_case.config);
        let result: Value = serde_json::from_str(&evaluate_json(&request_json)?)
            .map_err(|error| error.to_string())?;

        assert_eq!(
            result["faults"], test_case.expected_faults,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_path_threshold_overrides_when_evaluating_then_matches_in_authored_order()
-> Result<(), String> {
    let project_dir = TempDir::new().map_err(|error| error.to_string())?;
    let test_cases = [
        test_types::ThresholdEvaluationTestCase {
            description: "matching override raises both minima",
            config: json!({
                "select": ["SQBKX001", "SQBKX002"],
                "thresholds": {"min_audits_per_model": 1, "min_tests_per_model": 1},
                "threshold_overrides": [{
                    "paths": ["models/mart/**"],
                    "thresholds": {"min_audits_per_model": 2, "min_tests_per_model": 2},
                    "reason": "marts require stronger evidence"
                }],
                "cache": {"enabled": false}
            }),
            query_sql: "SELECT id + 1 AS id FROM prices",
            references: json!([]),
            expected_codes: &["SQBKX001", "SQBKX002"],
        },
        test_types::ThresholdEvaluationTestCase {
            description: "near miss keeps global minima",
            config: json!({
                "select": ["SQBKX001", "SQBKX002"],
                "thresholds": {"min_audits_per_model": 1, "min_tests_per_model": 1},
                "threshold_overrides": [{
                    "paths": ["models/staging/**"],
                    "thresholds": {"min_audits_per_model": 2, "min_tests_per_model": 2},
                    "reason": "staging requires stronger evidence"
                }],
                "cache": {"enabled": false}
            }),
            query_sql: "SELECT id + 1 AS id FROM prices",
            references: json!([]),
            expected_codes: &[],
        },
        test_types::ThresholdEvaluationTestCase {
            description: "last matching override wins",
            config: json!({
                "select": ["SQBKX001", "SQBKX002"],
                "thresholds": {"min_audits_per_model": 1, "min_tests_per_model": 1},
                "threshold_overrides": [
                    {
                        "paths": ["models/**"],
                        "thresholds": {"min_audits_per_model": 2, "min_tests_per_model": 2},
                        "reason": "all models require stronger evidence"
                    },
                    {
                        "paths": ["models/mart/**"],
                        "thresholds": {"min_audits_per_model": 1, "min_tests_per_model": 1},
                        "reason": "mart migration temporarily uses global minima"
                    }
                ],
                "cache": {"enabled": false}
            }),
            query_sql: "SELECT id + 1 AS id FROM prices",
            references: json!([]),
            expected_codes: &[],
        },
        test_types::ThresholdEvaluationTestCase {
            description: "audit and test overrides resolve independently",
            config: json!({
                "select": ["SQBKX001", "SQBKX002"],
                "thresholds": {"min_audits_per_model": 1, "min_tests_per_model": 1},
                "threshold_overrides": [{
                    "paths": ["models/mart/**"],
                    "thresholds": {"min_audits_per_model": 2},
                    "reason": "marts require an additional audit"
                }],
                "cache": {"enabled": false}
            }),
            query_sql: "SELECT id + 1 AS id FROM prices",
            references: json!([]),
            expected_codes: &["SQBKX001"],
        },
        test_types::ThresholdEvaluationTestCase {
            description: "matching override preserves passthrough exemption",
            config: json!({
                "select": ["SQBKX001", "SQBKX002"],
                "threshold_overrides": [{
                    "paths": ["models/mart/**"],
                    "thresholds": {"min_audits_per_model": 10, "min_tests_per_model": 10},
                    "reason": "marts require strong evidence"
                }],
                "cache": {"enabled": false}
            }),
            query_sql: "WITH upstream AS (SELECT * FROM __ref(\"market__stg__prices\")) SELECT id FROM upstream",
            references: json!([{"ref_kind": "ref", "ref_name": "market__stg__prices"}]),
            expected_codes: &[],
        },
    ];

    for test_case in &test_cases {
        let request_json = helpers::threshold_request(
            &project_dir,
            &test_case.config,
            test_case.query_sql,
            &test_case.references,
        );
        let result: Value = serde_json::from_str(&evaluate_json(&request_json)?)
            .map_err(|error| error.to_string())?;
        let codes: Vec<&str> = result["faults"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|fault| fault["code"].as_str())
            .collect();
        assert_eq!(codes, test_case.expected_codes, "{}", test_case.description);
    }
    Ok(())
}

#[test]
fn given_threshold_override_change_when_evaluating_then_ruleset_fingerprint_changes()
-> Result<(), String> {
    let project_dir = TempDir::new().map_err(|error| error.to_string())?;
    let test_cases = [test_types::ThresholdFingerprintTestCase {
        description: "path threshold changes the ruleset fingerprint",
        base_config: json!({
            "select": ["SQBKX002"],
            "cache": {"enabled": false}
        }),
        overridden_config: json!({
            "select": ["SQBKX002"],
            "threshold_overrides": [{
                "paths": ["models/mart/**"],
                "thresholds": {"min_tests_per_model": 2},
                "reason": "marts require two focused tests"
            }],
            "cache": {"enabled": false}
        }),
        expected_different: true,
    }];

    for test_case in &test_cases {
        let references = json!([]);
        let base_request = helpers::threshold_request(
            &project_dir,
            &test_case.base_config,
            "SELECT id + 1 AS id FROM prices",
            &references,
        );
        let overridden_request = helpers::threshold_request(
            &project_dir,
            &test_case.overridden_config,
            "SELECT id + 1 AS id FROM prices",
            &references,
        );
        let base_result: Value = serde_json::from_str(&evaluate_json(&base_request)?)
            .map_err(|error| error.to_string())?;
        let overridden_result: Value = serde_json::from_str(&evaluate_json(&overridden_request)?)
            .map_err(|error| error.to_string())?;
        let different =
            base_result["ruleset_fingerprint"] != overridden_result["ruleset_fingerprint"];

        assert_eq!(
            different, test_case.expected_different,
            "{}",
            test_case.description
        );
    }
    Ok(())
}
