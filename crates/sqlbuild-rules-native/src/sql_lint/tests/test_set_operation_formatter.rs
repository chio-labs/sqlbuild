use serde_json::{Value, json};

use crate::sql_lint::main::formatter::format_json;
use crate::sql_lint::tests::test_types;

const DIALECTS: [&str; 6] = [
    "bigquery",
    "databricks",
    "duckdb",
    "postgres",
    "snowflake",
    "tsql",
];

#[test]
fn given_set_operation_after_scalar_subquery_operand_when_formatting_then_keyword_stays_outer()
-> Result<(), String> {
    let test_cases = [
        test_types::FormatTestCase {
            description: "UNION ALL after WHERE scalar subquery",
            sql: "SELECT o.id, o.total FROM orders AS o WHERE o.total < (SELECT MAX(l.amount) FROM limits AS l) UNION ALL SELECT o.id, o.total FROM orders AS o",
            expected_sql: "SELECT\n  o.id,\n  o.total\nFROM orders AS o\nWHERE\n  o.total < (\n    SELECT MAX(l.amount)\n    FROM limits AS l\n  )\nUNION ALL\nSELECT\n  o.id,\n  o.total\nFROM orders AS o",
            expected_changed: true,
        },
        test_types::FormatTestCase {
            description: "EXCEPT after WHERE scalar subquery",
            sql: "SELECT o.id FROM orders AS o WHERE o.total > (SELECT MAX(l.amount) FROM limits AS l) EXCEPT SELECT o.id FROM orders AS o",
            expected_sql: "SELECT o.id\nFROM orders AS o\nWHERE\n  o.total > (\n    SELECT MAX(l.amount)\n    FROM limits AS l\n  )\nEXCEPT\nSELECT o.id\nFROM orders AS o",
            expected_changed: true,
        },
        test_types::FormatTestCase {
            description: "INTERSECT after WHERE scalar subquery",
            sql: "SELECT o.id FROM orders AS o WHERE o.total > (SELECT MAX(l.amount) FROM limits AS l) INTERSECT SELECT o.id FROM orders AS o",
            expected_sql: "SELECT o.id\nFROM orders AS o\nWHERE\n  o.total > (\n    SELECT MAX(l.amount)\n    FROM limits AS l\n  )\nINTERSECT\nSELECT o.id\nFROM orders AS o",
            expected_changed: true,
        },
    ];

    for dialect in DIALECTS {
        for test_case in &test_cases {
            let response = format_json(
                &json!({"version": 1, "sql": test_case.sql, "dialect": dialect}).to_string(),
            )?;
            let payload: Value =
                serde_json::from_str(&response).map_err(|error| error.to_string())?;
            assert_eq!(
                payload["sql"], test_case.expected_sql,
                "{dialect}: {}",
                test_case.description
            );
            assert_eq!(
                payload["changed"], test_case.expected_changed,
                "{dialect}: {}",
                test_case.description
            );
        }
    }
    Ok(())
}
