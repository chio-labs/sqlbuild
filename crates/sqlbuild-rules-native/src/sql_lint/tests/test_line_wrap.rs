use std::collections::HashMap;

use serde_json::{Value, json};

use crate::sql_lint::main::formatter::format_json;
use crate::sql_lint::tests::test_types;

#[test]
fn given_lines_over_the_width_when_formatting_then_each_wrap_rule_applies_idempotently()
-> Result<(), String> {
    let test_cases = [
        test_types::LineWrapTestCase {
            description: "function arguments go one per line",
            sql: "select coalesce(first_order_amount, second_order_amount, third_order_amount, fallback_amount) as amount from orders",
            line_width: 60,
            token_widths: &[],
            expected_sql: "SELECT\n  COALESCE(\n    first_order_amount,\n    second_order_amount,\n    third_order_amount,\n    fallback_amount\n  ) AS amount\nFROM orders",
        },
        test_types::LineWrapTestCase {
            description: "IN lists go one element per line",
            sql: "select order_id from orders where region in ('north', 'south', 'east', 'west', 'central', 'remote')",
            line_width: 50,
            token_widths: &[],
            expected_sql: "SELECT order_id\nFROM orders\nWHERE\n  region IN (\n    'north',\n    'south',\n    'east',\n    'west',\n    'central',\n    'remote'\n  )",
        },
        test_types::LineWrapTestCase {
            description: "window PARTITION BY and ORDER BY go on separate lines",
            sql: "select row_number() over (partition by customer_id, region_code order by ordered_at desc, order_id desc) as rank_in_customer from orders",
            line_width: 60,
            token_widths: &[],
            expected_sql: "SELECT\n  ROW_NUMBER() OVER (\n    PARTITION BY customer_id, region_code\n    ORDER BY ordered_at DESC, order_id DESC\n  ) AS rank_in_customer\nFROM orders",
        },
        test_types::LineWrapTestCase {
            description: "join conditions break before AND but not inside BETWEEN",
            sql: "select o.order_id from orders o join customers c on o.customer_id = c.customer_id and o.amount between 1 and 9 and o.store = c.store",
            line_width: 60,
            token_widths: &[],
            expected_sql: "SELECT o.order_id\nFROM orders o\nJOIN customers c\n  ON o.customer_id = c.customer_id\n  AND o.amount BETWEEN 1 AND 9\n  AND o.store = c.store",
        },
        test_types::LineWrapTestCase {
            description: "arithmetic chains break before operators",
            sql: "select first_amount + second_amount + third_amount + fourth_amount as total from orders",
            line_width: 50,
            token_widths: &[],
            expected_sql: "SELECT\n  first_amount\n    + second_amount\n    + third_amount\n    + fourth_amount AS total\nFROM orders",
        },
        test_types::LineWrapTestCase {
            description: "a top-level AND chain breaks before a nested group",
            sql: "select order_id from orders where cast(ordered_at as DATE) >= cast(@start as DATE) and cast(ordered_at as DATE) < cast(@end as DATE)",
            line_width: 60,
            token_widths: &[],
            expected_sql: "SELECT order_id\nFROM orders\nWHERE\n  CAST(ordered_at AS DATE) >= CAST(@start AS DATE)\n  AND CAST(ordered_at AS DATE) < CAST(@end AS DATE)",
        },
        test_types::LineWrapTestCase {
            description: "a long string literal is never broken",
            sql: "select 'a long literal that is wider than the configured line width' as note from orders",
            line_width: 40,
            token_widths: &[],
            expected_sql: "SELECT\n  'a long literal that is wider than the configured line width' AS note\nFROM orders",
        },
        test_types::LineWrapTestCase {
            description: "a line with a comment is never broken",
            sql: "select coalesce(first_amount, second_amount, third_amount) as amount -- keep\nfrom orders",
            line_width: 40,
            token_widths: &[],
            expected_sql: "SELECT\n  COALESCE(first_amount, second_amount, third_amount) AS amount -- keep\nFROM orders",
        },
        test_types::LineWrapTestCase {
            description: "a sentinel counts with the width of the text it stands for",
            sql: "select coalesce(__sqb_lint_0__, b) as amount from orders",
            line_width: 40,
            token_widths: &[("__SQB_LINT_0__", 30)],
            expected_sql: "SELECT\n  COALESCE(\n    __sqb_lint_0__,\n    b\n  ) AS amount\nFROM orders",
        },
        test_types::LineWrapTestCase {
            description: "lines within the width are unchanged",
            sql: "select coalesce(first_amount, second_amount) as amount from orders",
            line_width: 100,
            token_widths: &[],
            expected_sql: "SELECT COALESCE(first_amount, second_amount) AS amount\nFROM orders",
        },
    ];
    for test_case in &test_cases {
        let token_widths: HashMap<&str, usize> = test_case.token_widths.iter().copied().collect();
        let request = |sql: &str| {
            json!({
                "version": 1,
                "sql": sql,
                "dialect": "duckdb",
                "line_width": test_case.line_width,
                "token_widths": token_widths,
            })
            .to_string()
        };
        let response: Value = serde_json::from_str(&format_json(&request(test_case.sql))?)
            .map_err(|error| error.to_string())?;
        assert_eq!(
            response["sql"], test_case.expected_sql,
            "{}",
            test_case.description
        );
        let again: Value = serde_json::from_str(&format_json(&request(test_case.expected_sql))?)
            .map_err(|error| error.to_string())?;
        assert_eq!(again["changed"], false, "{}", test_case.description);
    }
    Ok(())
}
