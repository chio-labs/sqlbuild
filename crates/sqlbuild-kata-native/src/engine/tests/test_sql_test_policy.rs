use crate::engine::main::evaluate::evaluate_json;
use crate::engine::tests::{helpers, test_types};
use serde_json::{Value, json};
use tempfile::TempDir;

#[test]
fn given_sql_test_facts_when_evaluating_project_policy_then_returns_expected_faults()
-> Result<(), String> {
    let project_dir = TempDir::new().map_err(|error| error.to_string())?;
    let mut misplaced_test = helpers::sql_test_fact(
        "quality/test_orders__paid.sql",
        Some("orders: keeps paid orders"),
        json!([]),
    );
    misplaced_test["ownership_root"] = json!("quality");
    let mut scope = helpers::scope_index();
    scope["resources"] = json!([
        {
            "identity": "model:stg_orders", "kind": "model", "name": "stg_orders",
            "path": "models/commerce/staging/stg_orders.sql", "ownership_root": "models",
            "ownership_root_kind": "model"
        },
        {
            "identity": "model:fact_orders", "kind": "model", "name": "fact_orders",
            "path": "models/commerce/marts/fact_orders.sql", "ownership_root": "models",
            "ownership_root_kind": "model"
        },
        {
            "identity": "model:daily_revenue", "kind": "model", "name": "daily_revenue",
            "path": "models/finance/marts/daily_revenue.sql", "ownership_root": "models",
            "ownership_root_kind": "model"
        },
        {
            "identity": "model:race__mart_v_entry", "kind": "model",
            "name": "race__mart_v_entry",
            "path": "models/race/marts/race__mart_v_entry.sql", "ownership_root": "models",
            "ownership_root_kind": "model"
        }
    ]);
    let mut macro_test = helpers::sql_test_fact(
        "tests/unit/macros/test_normalize__trims.sql",
        Some("normalize_status__trims_spaces"),
        json!([]),
    );
    macro_test["mode"] = json!("macro");
    macro_test["tested_resources"] = json!([{"kind": "macro", "name": "normalize_status"}]);
    let test_cases = [
        test_types::SqlTestPolicyTestCase {
            description: "canonical roots run without a model anchor",
            code: "SQBKT001",
            tests: json!([misplaced_test]),
            scenarios: json!([{
                "source_path": "quality/orders__paid.sql", "ownership_root": "quality",
                "name": "orders__paid", "description": "Paid orders remain visible",
                "expected_model_names": [], "assertion_names": [],
                "assertion_target_model_names": [], "target_model_names": []
            }]),
            scope_index: helpers::scope_index(),
            config: json!({}),
            expected_fault_count: 2,
            expected_evaluated_models: 0,
            expected_paths: &["quality/orders__paid.sql", "quality/test_orders__paid.sql"],
        },
        test_types::SqlTestPolicyTestCase {
            description: "filename grammar checks unit and scenario paths",
            code: "SQBKT002",
            tests: json!([
                helpers::sql_test_fact(
                    "tests/unit/test_orders__keeps_paid.sql",
                    Some("orders: keeps paid orders"),
                    json!([])
                ),
                helpers::sql_test_fact(
                    "tests/unit/orders.sql",
                    Some("orders: excludes cancelled orders"),
                    json!([])
                ),
                helpers::sql_test_fact(
                    "tests/unit/test_race__mart_v_entry__returns_current.sql",
                    Some("race__mart_v_entry__returns_current_entries"),
                    json!(["race__mart_v_entry"])
                )
            ]),
            scenarios: json!([{
                "source_path": "tests/scenarios/daily_revenue.sql",
                "ownership_root": "tests/scenarios", "name": "daily_revenue",
                "description": "Daily revenue includes successful payments",
                "expected_model_names": [], "assertion_names": [],
                "assertion_target_model_names": [], "target_model_names": []
            }]),
            scope_index: scope.clone(),
            config: json!({}),
            expected_fault_count: 2,
            expected_evaluated_models: 0,
            expected_paths: &["tests/scenarios/daily_revenue.sql", "tests/unit/orders.sql"],
        },
        test_types::SqlTestPolicyTestCase {
            description: "resolved ownership uses LCA, pipeline, and direct resource paths",
            code: "SQBKT003",
            tests: json!([
                helpers::sql_test_fact(
                    "tests/unit/commerce/staging/test_stg_orders__paid.sql",
                    Some("stg_orders__keeps_paid_orders"),
                    json!(["stg_orders"])
                ),
                helpers::sql_test_fact(
                    "tests/unit/commerce/test_order_pipeline__paid.sql",
                    Some("commerce__keeps_paid_orders"),
                    json!(["stg_orders", "fact_orders"])
                ),
                helpers::sql_test_fact(
                    "tests/unit/wrong/test_pipeline__revenue.sql",
                    Some("pipeline__calculates_revenue"),
                    json!(["stg_orders", "daily_revenue"])
                ),
                macro_test
            ]),
            scenarios: json!([]),
            scope_index: scope,
            config: json!({"sql_tests": {"pipeline_directory": "chains"}}),
            expected_fault_count: 1,
            expected_evaluated_models: 0,
            expected_paths: &["tests/unit/wrong/test_pipeline__revenue.sql"],
        },
        test_types::SqlTestPolicyTestCase {
            description: "structured names require explicit target-aware behavior",
            code: "SQBKT004",
            tests: json!([
                helpers::sql_test_fact(
                    "tests/unit/test_orders__paid.sql",
                    Some("orders__keeps_paid_orders__after_capture"),
                    json!(["orders"])
                ),
                helpers::sql_test_fact(
                    "tests/unit/test_orders__basic.sql",
                    Some("orders__basic"),
                    json!(["orders"])
                ),
                helpers::sql_test_fact("tests/unit/test_orders__paid.sql", None, json!(["orders"])),
                helpers::sql_test_fact(
                    "tests/unit/test_orders__paid.sql",
                    Some("payments__keeps_paid_orders"),
                    json!(["orders"])
                ),
                helpers::sql_test_fact(
                    "tests/unit/test_race__mart_v_entry__returns_current.sql",
                    Some("race__mart_v_entry__returns_current_entries"),
                    json!(["race__mart_v_entry"])
                )
            ]),
            scenarios: json!([]),
            scope_index: helpers::scope_index(),
            config: json!({}),
            expected_fault_count: 3,
            expected_evaluated_models: 0,
            expected_paths: &[
                "tests/unit/test_orders__basic.sql",
                "tests/unit/test_orders__paid.sql",
                "tests/unit/test_orders__paid.sql",
            ],
        },
        test_types::SqlTestPolicyTestCase {
            description: "scenario descriptions reject generic numbering",
            code: "SQBKT101",
            tests: json!([]),
            scenarios: json!([
                {
                    "source_path": "tests/scenarios/orders__paid.sql",
                    "ownership_root": "tests/scenarios", "name": "orders__paid",
                    "description": "Paid orders remain visible", "expected_model_names": [],
                    "assertion_names": [], "assertion_target_model_names": [],
                    "target_model_names": []
                },
                {
                    "source_path": "tests/scenarios/orders__case_1.sql",
                    "ownership_root": "tests/scenarios", "name": "orders__case_1",
                    "description": "case 1", "expected_model_names": [],
                    "assertion_names": [], "assertion_target_model_names": [],
                    "target_model_names": []
                }
            ]),
            scope_index: helpers::scope_index(),
            config: json!({}),
            expected_fault_count: 1,
            expected_evaluated_models: 0,
            expected_paths: &["tests/scenarios/orders__case_1.sql"],
        },
        test_types::SqlTestPolicyTestCase {
            description: "path-scoped ignore suppresses a test policy fault",
            code: "SQBKT004",
            tests: json!([helpers::sql_test_fact(
                "tests/unit/test_orders__paid.sql",
                None,
                json!(["orders"])
            )]),
            scenarios: json!([]),
            scope_index: helpers::scope_index(),
            config: json!({"rule_ignores": [{
                "rules": ["SQBKT004"], "paths": ["tests/unit/**"],
                "reason": "tracked naming migration"
            }]}),
            expected_fault_count: 0,
            expected_evaluated_models: 0,
            expected_paths: &[],
        },
    ];

    for test_case in test_cases {
        let result = helpers::sql_test_policy_evaluation(
            &project_dir,
            test_case.code,
            test_case.tests,
            test_case.scenarios,
            test_case.scope_index,
            test_case.config,
        )?;
        let paths: Vec<&str> = result["faults"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|fault| fault["path"].as_str())
            .collect();
        assert_eq!(
            result["faults"].as_array().map(Vec::len),
            Some(test_case.expected_fault_count),
            "{}",
            test_case.description
        );
        assert_eq!(
            result["evaluated_models"], test_case.expected_evaluated_models,
            "{}",
            test_case.description
        );
        assert_eq!(paths, test_case.expected_paths, "{}", test_case.description);
    }
    Ok(())
}

#[test]
fn given_test_fact_change_when_evaluating_cached_project_rule_then_model_cache_is_invalidated()
-> Result<(), String> {
    let project_dir = TempDir::new().map_err(|error| error.to_string())?;
    let test_cases = [test_types::SqlTestPolicyCacheTestCase {
        description: "test fact change invalidates model cache identity",
        expected_first_misses: 1,
        expected_second_hits: 0,
        expected_second_misses: 1,
    }];
    for test_case in &test_cases {
        let first: Value = serde_json::from_str(&evaluate_json(
            &helpers::cached_sql_test_policy_request(&project_dir, None),
        )?)
        .map_err(|error| error.to_string())?;
        let second: Value =
            serde_json::from_str(&evaluate_json(&helpers::cached_sql_test_policy_request(
                &project_dir,
                Some("orders: keeps paid orders"),
            ))?)
            .map_err(|error| error.to_string())?;
        assert_eq!(
            first["cache_misses"], test_case.expected_first_misses,
            "{}",
            test_case.description
        );
        assert_eq!(
            second["cache_hits"], test_case.expected_second_hits,
            "{}",
            test_case.description
        );
        assert_eq!(
            second["cache_misses"], test_case.expected_second_misses,
            "{}",
            test_case.description
        );
    }
    Ok(())
}
