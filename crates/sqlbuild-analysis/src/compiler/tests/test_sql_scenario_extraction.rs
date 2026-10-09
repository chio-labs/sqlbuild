use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::compiler::main::sql_scenario_extraction::extract_scenario_json;
use crate::compiler::tests::test_types::ScenarioExtractionTestCase;

#[test]
fn given_scenarios_when_extracting_natively_then_outcomes_are_returned() {
    let syntax = LexicalSyntax {
        line_comment_prefixes: vec!["--".to_owned()],
        ..LexicalSyntax::default()
    };
    let test_cases = [
        ScenarioExtractionTestCase {
            description: "fixtures, helpers and expected results without cross references",
            sql: "WITH helper AS (SELECT 1 AS id), __source__raw_orders AS (SELECT 2 AS id), \
                  __expected__orders AS (SELECT 1 AS id) SELECT 1",
            expected_json: r#"{"scenario":{"authored":[["helper","SELECT 1 AS id"],["__source__raw_orders","SELECT 2 AS id"]],"expected":[["__expected__orders","SELECT 1 AS id"]],"assertions":[],"sourceFixtures":["raw_orders"],"refFixtures":[],"seedFixtures":[],"dbtRefFixtures":[],"expectedModels":["orders"],"assertionNames":[]}}"#,
        },
        ScenarioExtractionTestCase {
            description: "expected results and assertions reading a CTE pass the independence check",
            sql: "WITH helper AS (SELECT 1 AS id), __source__raw AS (SELECT id FROM helper), \
                  __expected__orders AS (SELECT 1 AS id), __assert__positive AS (SELECT 1) SELECT 1",
            expected_json: r#"{"scenario":{"authored":[["helper","SELECT 1 AS id"],["__source__raw","SELECT id FROM helper"]],"expected":[["__expected__orders","SELECT 1 AS id"]],"assertions":[["__assert__positive","SELECT 1"]],"sourceFixtures":["raw"],"refFixtures":[],"seedFixtures":[],"dbtRefFixtures":[],"expectedModels":["orders"],"assertionNames":["positive"]}}"#,
        },
        ScenarioExtractionTestCase {
            description: "an expected result naming the assertion prefix passes the independence check",
            sql: "WITH __source__raw AS (SELECT 1), __expected__orders AS (SELECT '__ASSERT__' AS x) \
                  SELECT 1",
            expected_json: r#"{"scenario":{"authored":[["__source__raw","SELECT 1"]],"expected":[["__expected__orders","SELECT '__ASSERT__' AS x"]],"assertions":[],"sourceFixtures":["raw"],"refFixtures":[],"seedFixtures":[],"dbtRefFixtures":[],"expectedModels":["orders"],"assertionNames":[]}}"#,
        },
        ScenarioExtractionTestCase {
            description: "a macro mock raises Python's error",
            sql: "WITH __source__raw AS (SELECT 1), __macro__tidy AS (SELECT 'x'), \
                  __expected__orders AS (SELECT 1 AS id) SELECT 1",
            expected_json: r#"{"error":"SQL scenario 'tests/scenarios/orders.sql' does not support macro mock CTE '__macro__tidy'. Scenarios run real project macros; use SQL unit tests for macro mocks."}"#,
        },
        ScenarioExtractionTestCase {
            description: "a bare fixture prefix raises Python's error before later CTEs",
            sql: "WITH __seed__ AS (SELECT 1), __macro__tidy AS (SELECT 'x') SELECT 1",
            expected_json: r#"{"error":"SQL scenario 'tests/scenarios/orders.sql' must use __seed__<seed> to identify a target"}"#,
        },
        ScenarioExtractionTestCase {
            description: "a scenario without fixtures raises Python's error",
            sql: "WITH __expected__orders AS (SELECT 1 AS id) SELECT 1",
            expected_json: r#"{"error":"SQL scenario 'tests/scenarios/orders.sql' must define at least one __source__*, __ref__*, __seed__*, or __dbt_ref__* fixture CTE"}"#,
        },
        ScenarioExtractionTestCase {
            description: "a scenario without checks raises Python's error",
            sql: "WITH __dbt_ref__shop__orders AS (SELECT 1 AS id)",
            expected_json: r#"{"error":"SQL scenario 'tests/scenarios/orders.sql' must define at least one __expected__<model> or __assert__<assertion> CTE"}"#,
        },
        ScenarioExtractionTestCase {
            description: "a quoted CTE name is Python's scanner error",
            sql: "WITH \"__source__raw\" AS (SELECT 1), __expected__orders AS (SELECT 1 AS id)",
            expected_json: r#"{"error":"SQL scenario 'tests/scenarios/orders.sql' expected a CTE name"}"#,
        },
        ScenarioExtractionTestCase {
            description: "an unclosed body is Python's scanner error naming the scenario context",
            sql: "WITH __source__raw AS (SELECT 1",
            expected_json: r#"{"error":"SQL scenario contains an unclosed parenthesis"}"#,
        },
        ScenarioExtractionTestCase {
            description: "a materialization hint is Python's scanner error",
            sql: "WITH __source__raw AS NOT MATERIALIZED (SELECT 1), __expected__orders AS (SELECT 1)",
            expected_json: r#"{"error":"SQL scenario 'tests/scenarios/orders.sql' CTE '__source__raw' must not use AS NOT MATERIALIZED; materialization hints are not supported in SQL scenario CTEs"}"#,
        },
        ScenarioExtractionTestCase {
            description: "a keyword matched by case mapping reads as the keyword",
            sql: "w\u{131}th __source__raw AS (SELECT 1), __expected__orders AS (SELECT 1 AS id)",
            expected_json: r#"{"scenario":{"authored":[["__source__raw","SELECT 1"]],"expected":[["__expected__orders","SELECT 1 AS id"]],"assertions":[],"sourceFixtures":["raw"],"refFixtures":[],"seedFixtures":[],"dbtRefFixtures":[],"expectedModels":["orders"],"assertionNames":[]}}"#,
        },
        ScenarioExtractionTestCase {
            description: "an expected result reading an assertion through a helper fails",
            sql: "WITH __source__raw AS (SELECT 1), helper AS (SELECT * FROM __assert__positive), \
                  __expected__orders AS (SELECT * FROM helper), __assert__positive AS (SELECT 1) SELECT 1",
            expected_json: r#"{"error":"SQL scenario 'tests/scenarios/orders.sql' check CTE '__expected__orders' must not depend on '__assert__positive' through 'helper'; expected results and assertions must be independent"}"#,
        },
        ScenarioExtractionTestCase {
            description: "an assertion defining a nested expected result fails",
            sql: "WITH __source__raw AS (SELECT 1), __expected__orders AS (SELECT 1), \
                  __assert__positive AS (WITH __expected__x AS (SELECT 1) SELECT * FROM __expected__x) SELECT 1",
            expected_json: r#"{"error":"SQL scenario 'tests/scenarios/orders.sql' check CTE '__assert__positive' must not define expected result CTE '__expected__x'; expected results and assertions must be independent"}"#,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            extract_scenario_json(test_case.sql, "tests/scenarios/orders.sql", &syntax),
            Ok(test_case.expected_json.to_owned()),
            "{}",
            test_case.description
        );
    }
}
