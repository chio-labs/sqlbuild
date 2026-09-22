use serde_json::{Value, json};

use crate::sql_lint::main::engine::lint_json;
use crate::sql_lint::tests::test_types;

#[test]
fn given_empty_fixture_context_when_linting_projected_star_then_only_canonical_inputs_pass()
-> Result<(), String> {
    let test_cases = [
        test_types::EmptyFixtureLintTestCase {
            description: "canonical ref fixture",
            sql: "WITH __ref__orders AS (SELECT * FROM __empty_fixture()) SELECT 1",
            allows_empty_fixture_star: true,
            expected_diagnostic_count: 0,
        },
        test_types::EmptyFixtureLintTestCase {
            description: "canonical source fixture",
            sql: "WITH __source__web__orders AS (SELECT * FROM __empty_fixture()) SELECT 1",
            allows_empty_fixture_star: true,
            expected_diagnostic_count: 0,
        },
        test_types::EmptyFixtureLintTestCase {
            description: "ordinary SQL has no intrinsic exemption",
            sql: "SELECT * FROM __empty_fixture()",
            allows_empty_fixture_star: false,
            expected_diagnostic_count: 1,
        },
        test_types::EmptyFixtureLintTestCase {
            description: "expected fixture remains controlled",
            sql: "WITH __expected__orders AS (SELECT * FROM __empty_fixture()) SELECT 1",
            allows_empty_fixture_star: true,
            expected_diagnostic_count: 1,
        },
        test_types::EmptyFixtureLintTestCase {
            description: "additional projection is not canonical",
            sql: "WITH __ref__orders AS (SELECT *, 1 AS extra FROM __empty_fixture()) SELECT 1",
            allows_empty_fixture_star: true,
            expected_diagnostic_count: 1,
        },
    ];
    for test_case in test_cases {
        let response = lint_json(
            &json!({
                "version": 1,
                "sql": test_case.sql,
                "dialect": "snowflake",
                "enabled_rules": ["SQBRSQL021"],
                "allows_empty_fixture_star": test_case.allows_empty_fixture_star
            })
            .to_string(),
        )?;
        let payload: Value = serde_json::from_str(&response).map_err(|error| error.to_string())?;
        assert_eq!(
            payload["diagnostics"].as_array().map_or(0, Vec::len),
            test_case.expected_diagnostic_count,
            "{}",
            test_case.description
        );
    }
    Ok(())
}
