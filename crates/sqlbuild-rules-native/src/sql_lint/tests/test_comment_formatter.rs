use serde_json::{Value, json};

use crate::sql_lint::main::formatter::format_json;
use crate::sql_lint::tests::test_types;

#[test]
fn given_leading_cte_comments_when_formatting_then_comments_stay_above_their_cte()
-> Result<(), String> {
    let test_cases = [
        test_types::FormatTestCase {
            description: "leading comment before a middle CTE stays above it",
            sql: "WITH\nupstream AS (\n  SELECT * FROM orders\n),\n\n-- Explains the next CTE: line one,\n-- line two.\ndistinct_rows AS (\n    SELECT order_id FROM upstream GROUP BY ALL\n)\n\nSELECT order_id FROM distinct_rows",
            expected_sql: "WITH upstream AS (\n  SELECT\n    *\n  FROM orders\n),\n-- Explains the next CTE: line one,\n-- line two.\ndistinct_rows AS (\n  SELECT\n    order_id\n  FROM upstream\n  GROUP BY ALL\n)\nSELECT\n  order_id\nFROM distinct_rows",
            expected_changed: true,
        },
        test_types::FormatTestCase {
            description: "formatted leading CTE comment is idempotent",
            sql: "WITH upstream AS (\n  SELECT\n    *\n  FROM orders\n),\n-- Explains the next CTE: line one,\n-- line two.\ndistinct_rows AS (\n  SELECT\n    order_id\n  FROM upstream\n  GROUP BY ALL\n)\nSELECT\n  order_id\nFROM distinct_rows",
            expected_sql: "WITH upstream AS (\n  SELECT\n    *\n  FROM orders\n),\n-- Explains the next CTE: line one,\n-- line two.\ndistinct_rows AS (\n  SELECT\n    order_id\n  FROM upstream\n  GROUP BY ALL\n)\nSELECT\n  order_id\nFROM distinct_rows",
            expected_changed: false,
        },
        test_types::FormatTestCase {
            description: "leading comment before the first CTE stays above it",
            sql: "WITH\n-- Explains the first CTE.\nupstream AS (SELECT * FROM orders)\nSELECT order_id FROM upstream",
            expected_sql: "WITH\n-- Explains the first CTE.\nupstream AS (\n  SELECT\n    *\n  FROM orders\n)\nSELECT\n  order_id\nFROM upstream",
            expected_changed: true,
        },
        test_types::FormatTestCase {
            description: "leading comment before the last of three CTEs stays above it",
            sql: "WITH a AS (SELECT 1 AS x),\nb AS (SELECT x FROM a),\n  /* Explains the last CTE. */\nc AS (SELECT x FROM b)\nSELECT x FROM c",
            expected_sql: "WITH a AS (\n  SELECT\n    1 AS x\n), b AS (\n  SELECT\n    x\n  FROM a\n),\n/* Explains the last CTE. */\nc AS (\n  SELECT\n    x\n  FROM b\n)\nSELECT\n  x\nFROM c",
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
