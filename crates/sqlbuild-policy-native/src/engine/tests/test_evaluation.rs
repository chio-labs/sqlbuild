use serde_json::{Value, json};
use tempfile::TempDir;

use crate::engine::main::evaluate::evaluate_json;
use crate::engine::tests::helpers;
use crate::engine::tests::test_types;
use crate::rules::_helpers::evaluation::normalize_policy_sql;

#[test]
fn given_repeated_native_evaluation_when_faulting_then_returns_deterministic_complete_facts()
-> Result<(), String> {
    let test_cases = [test_types::NativeEvaluationTestCase {
        description: "repeated native evaluation preserves every fault fact",
        config: json!({
            "select": ["SQBPC101"],
            "cache": {"enabled": false, "require_cacheable": false}
        }),
        expected_faults: json!([{
            "code": "SQBPC101",
            "path": "models/mart/market__mart__prices.sql",
            "line": 1,
            "column": 1,
            "message": "models must declare an enforced output contract",
            "remediation": "Declare contract enforced and list the authoritative output columns in MODEL()."
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
            "select": ["SQBPC101"],
            "cache": {"enabled": false, "require_cacheable": false},
            "rule_ignores": [{
                "rules": ["SQBPC"],
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
fn given_snowflake_expression_when_evaluating_policy_then_uses_project_dialect()
-> Result<(), String> {
    let project_dir = TempDir::new().map_err(|error| error.to_string())?;
    let config = json!({
        "select": ["SQBPC101"],
        "cache": {"enabled": false}
    });
    let mut request: Value = serde_json::from_str(&helpers::request(&project_dir, &config))
        .map_err(|error| error.to_string())?;
    request["dialect"] = json!("snowflake");
    request["models"][0]["query_sql"] = json!(concat!(
        "SELECT * EXCLUDE (ignored), ",
        "TRANSFORM(values, leg INT -> leg + 1) AS adjusted, ",
        "payload:product_id::STRING AS product_id, ",
        "CAST(amounts AS ARRAY(NUMBER(38, 10))) AS amounts, ",
        "OBJECT_CONSTRUCT_KEEP_NULL('group_id', group_id) AS details, ",
        "FROM __table_fn(\"inventory_items\")(42)"
    ));

    let result: Value = serde_json::from_str(&evaluate_json(&request.to_string())?)
        .map_err(|error| error.to_string())?;

    assert_eq!(result["faults"][0]["code"], "SQBPC101");
    Ok(())
}

#[test]
fn given_snowflake_parser_extensions_when_normalizing_then_preserves_source_positions() {
    let sql = concat!(
        "SELECT * EXCLUDE (\n  ignored,\n  obsolete\n), ",
        "TRANSFORM(values, leg INT -> leg + 1),\n",
        "'__table_fn(\"quoted\")(7)', /* leg INT -> unchanged */ payload:key::STRING,\n",
        "CAST(amounts AS ARRAY(\n  NUMBER(38, 10)\n)) AS amounts\n",
        "FROM __table_fn(\"prices)archive\")(42)"
    );

    let normalized = normalize_policy_sql("snowflake", sql);

    assert_eq!(normalized.len(), sql.len());
    assert_eq!(normalized.lines().count(), sql.lines().count());
    assert!(normalized.contains("leg     -> leg + 1"));
    assert!(normalized.contains("'__table_fn(\"quoted\")(7)'"));
    assert!(normalized.contains("/* leg INT -> unchanged */"));
    assert!(normalized.contains("__table_fn(\"prices)archive\", 42)"));
    let duckdb = normalize_policy_sql("duckdb", sql);
    assert!(duckdb.contains("leg INT -> leg + 1"));
    assert!(duckdb.contains("'__table_fn(\"quoted\")(7)'"));
}

#[test]
fn given_deep_valid_expression_when_evaluating_policy_then_parser_budget_is_sufficient()
-> Result<(), String> {
    let project_dir = TempDir::new().map_err(|error| error.to_string())?;
    let config = json!({
        "select": ["SQBPC101"],
        "cache": {"enabled": false}
    });
    let mut request: Value = serde_json::from_str(&helpers::request(&project_dir, &config))
        .map_err(|error| error.to_string())?;
    let expression = format!("{}1{}", "COALESCE(".repeat(55), ", 0)".repeat(55));
    request["models"][0]["query_sql"] = json!(format!("SELECT {expression} AS value"));

    let result: Value = serde_json::from_str(&evaluate_json(&request.to_string())?)
        .map_err(|error| error.to_string())?;

    assert_eq!(result["faults"][0]["code"], "SQBPC101");
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
                "select": ["SQBPT201", "SQBPT202"],
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
            expected_codes: &["SQBPT201", "SQBPT202"],
        },
        test_types::ThresholdEvaluationTestCase {
            description: "near miss keeps global minima",
            config: json!({
                "select": ["SQBPT201", "SQBPT202"],
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
                "select": ["SQBPT201", "SQBPT202"],
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
                "select": ["SQBPT201", "SQBPT202"],
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
            expected_codes: &["SQBPT201"],
        },
        test_types::ThresholdEvaluationTestCase {
            description: "matching override preserves passthrough exemption",
            config: json!({
                "select": ["SQBPT201", "SQBPT202"],
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
            "select": ["SQBPT202"],
            "cache": {"enabled": false}
        }),
        overridden_config: json!({
            "select": ["SQBPT202"],
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
