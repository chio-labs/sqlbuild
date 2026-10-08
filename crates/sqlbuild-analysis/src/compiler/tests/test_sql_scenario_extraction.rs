use crate::compiler::main::sql_scenario_extraction::extract_scenario_json;
use crate::compiler::tests::test_types::ScenarioExtractionTestCase;

#[test]
fn given_scenarios_when_extracting_natively_then_python_payloads_or_deferrals_are_returned() {
    let test_cases = [
        ScenarioExtractionTestCase {
            description: "fixtures, helpers, expected results and assertions are classified",
            sql: "WITH helper AS (SELECT 1 AS id), __source__raw_orders AS (SELECT id FROM helper), \
                  __expected__orders AS (SELECT 1 AS id), __assert__positive AS (SELECT 1) SELECT 1",
            expected_json: Some(
                r#"{"authored":[["helper","SELECT 1 AS id"],["__source__raw_orders","SELECT id FROM helper"]],"expected":[["__expected__orders","SELECT 1 AS id"]],"assertions":[["__assert__positive","SELECT 1"]],"sourceFixtures":["raw_orders"],"refFixtures":[],"seedFixtures":[],"dbtRefFixtures":[],"expectedModels":["orders"],"assertionNames":["positive"]}"#,
            ),
        },
        ScenarioExtractionTestCase {
            description: "a macro mock defers so Python raises",
            sql: "WITH __source__raw AS (SELECT 1), __macro__tidy AS (SELECT 'x'), \
                  __expected__orders AS (SELECT 1 AS id) SELECT 1",
            expected_json: None,
        },
        ScenarioExtractionTestCase {
            description: "a quoted CTE name defers to Python's scanner fallback",
            sql: "WITH \"__source__raw\" AS (SELECT 1), __expected__orders AS (SELECT 1 AS id)",
            expected_json: None,
        },
        ScenarioExtractionTestCase {
            description: "a keyword Python would match by case mapping defers",
            sql: "w\u{131}th __source__raw AS (SELECT 1), __expected__orders AS (SELECT 1 AS id)",
            expected_json: None,
        },
        ScenarioExtractionTestCase {
            description: "a scenario without fixtures defers so Python raises",
            sql: "WITH __expected__orders AS (SELECT 1 AS id) SELECT 1",
            expected_json: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            extract_scenario_json(test_case.sql, "tests/scenarios/orders.sql"),
            Ok(test_case.expected_json.map(str::to_owned)),
            "{}",
            test_case.description
        );
    }
}
