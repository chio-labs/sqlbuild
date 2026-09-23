use serde_json::{Value, json};

use crate::sql_lint::main::formatter::format_json;
use crate::sql_lint::tests::test_types;

#[test]
fn given_mixed_values_relations_when_formatting_then_each_authored_form_is_preserved()
-> Result<(), String> {
    let test_cases = [
        test_types::FormatTestCase {
            description: "mixed values relations preserve parenthesized relation first",
            sql: "SELECT * FROM (VALUES (1, 2)) AS first_values(a, b) UNION ALL SELECT * FROM VALUES (3, 4)",
            expected_sql: "SELECT\n  *\nFROM (VALUES (1, 2)) AS first_values(a, b)\nUNION ALL\nSELECT\n  *\nFROM VALUES (3, 4)",
            expected_changed: true,
        },
        test_types::FormatTestCase {
            description: "mixed values relations preserve unparenthesized relation first",
            sql: "SELECT * FROM VALUES (1, 2) UNION ALL SELECT * FROM (VALUES (3, 4)) AS second_values(a, b)",
            expected_sql: "SELECT\n  *\nFROM VALUES (1, 2)\nUNION ALL\nSELECT\n  *\nFROM (VALUES (3, 4)) AS second_values(a, b)",
            expected_changed: true,
        },
        test_types::FormatTestCase {
            description: "mixed values relations inside joined subquery preserve authored forms",
            sql: "SELECT base.id FROM items AS base JOIN (SELECT * FROM (VALUES (1)) AS first_values(id) UNION ALL SELECT * FROM VALUES (2)) AS mixed ON base.id = mixed.id",
            expected_sql: "SELECT\n  base.id\nFROM items AS base\nJOIN (\n  SELECT\n    *\n  FROM (VALUES (1)) AS first_values(id)\n  UNION ALL\n  SELECT\n    *\n  FROM VALUES (2)\n) AS mixed\n  ON base.id = mixed.id",
            expected_changed: true,
        },
        test_types::FormatTestCase {
            description: "values text in string and comment is ignored",
            sql: "-- VALUES and FROM VALUES are examples\nSELECT 'VALUES' AS label FROM (VALUES (1)) AS first_values(id) UNION ALL SELECT * FROM VALUES (2)",
            expected_sql: "-- VALUES and FROM VALUES are examples\nSELECT\n  'VALUES' AS label\nFROM (VALUES (1)) AS first_values(id)\nUNION ALL\nSELECT\n  *\nFROM VALUES (2)",
            expected_changed: true,
        },
    ];

    for test_case in &test_cases {
        let response = format_json(
            &json!({"version": 1, "sql": test_case.sql, "dialect": "snowflake"}).to_string(),
        )?;
        let payload: Value = serde_json::from_str(&response).map_err(|error| error.to_string())?;
        assert_eq!(
            payload["sql"], test_case.expected_sql,
            "{}",
            test_case.description
        );
        assert_eq!(
            payload["changed"], test_case.expected_changed,
            "{}",
            test_case.description
        );
    }
    Ok(())
}
