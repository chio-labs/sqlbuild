use serde_json::{Value, json};

use crate::sql_lint::main::engine::lint_json;
use crate::sql_lint::tests::test_types::{
    DynamicOutputStarLintTestCase, QualificationExemptLintTestCase,
};

#[test]
fn given_exempt_macro_output_when_linting_qualification_then_only_authored_columns_are_judged()
-> Result<(), String> {
    let test_cases = [
        QualificationExemptLintTestCase {
            description: "a caller's bare column beside qualified macro output passes",
            sql: "SELECT order_id, orders.amount - orders.discount AS net FROM orders",
            exempt: "orders.amount - orders.discount",
            expected_count: 0,
        },
        QualificationExemptLintTestCase {
            description: "the caller's own mix still fails",
            sql: "SELECT order_id, orders.status, orders.amount - orders.discount AS net FROM orders",
            exempt: "orders.amount - orders.discount",
            expected_count: 1,
        },
    ];
    for test_case in test_cases {
        let start: usize = test_case
            .sql
            .find(test_case.exempt)
            .ok_or("exempt text should be in the SQL")?;
        let response = lint_json(
            &json!({
                "version": 1,
                "sql": test_case.sql,
                "dialect": "duckdb",
                "enabled_rules": ["SQBRSQL028"],
                "qualification_exempt_spans": [[start, start + test_case.exempt.len()]],
            })
            .to_string(),
        )?;
        let payload: Value = serde_json::from_str(&response).map_err(|error| error.to_string())?;
        let diagnostics = payload["diagnostics"]
            .as_array()
            .ok_or("diagnostics should be an array")?;

        assert_eq!(
            diagnostics.len(),
            test_case.expected_count,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_compiler_proven_dynamic_output_when_linting_then_only_terminal_star_is_exempt()
-> Result<(), String> {
    let test_cases = [DynamicOutputStarLintTestCase {
        description: "unrelated CTE star remains controlled",
        sql: "WITH pivot_input AS (SELECT customer_id, category, amount FROM orders), \
final AS (SELECT * FROM pivot_input PIVOT(MAX(amount) FOR category IN (ANY))), \
unrelated AS (SELECT * FROM pivot_input) SELECT * FROM final",
        expected_count: 1,
        expected_prefix: "unrelated AS (SELECT ",
    }];
    for test_case in test_cases {
        let response = lint_json(
            &json!({
                "version": 1,
                "sql": test_case.sql,
                "dialect": "snowflake",
                "enabled_rules": ["SQBRSQL021"],
                "allows_dynamic_output_star": true,
            })
            .to_string(),
        )?;
        let payload: Value = serde_json::from_str(&response).map_err(|error| error.to_string())?;
        let diagnostics = payload["diagnostics"]
            .as_array()
            .ok_or("diagnostics should be an array")?;

        assert_eq!(
            diagnostics.len(),
            test_case.expected_count,
            "{}",
            test_case.description
        );
        let start = diagnostics[0]["start"].as_u64().unwrap_or_default() as usize;
        assert!(
            test_case.sql[..start].ends_with(test_case.expected_prefix),
            "{}",
            test_case.description
        );
    }
    Ok(())
}
