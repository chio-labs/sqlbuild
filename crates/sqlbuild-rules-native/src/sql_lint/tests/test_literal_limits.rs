use serde_json::{Value, json};

use crate::sql_lint::main::engine::lint_json;
use crate::sql_lint::tests::test_types::LiteralLimitTestCase;

#[test]
fn given_literal_forms_when_linting_then_safe_concatenations_or_named_refusals_are_returned()
-> Result<(), String> {
    let test_cases = [
        LiteralLimitTestCase {
            description: "ordinary string",
            sql: "SELECT 'pending shipped'",
            dialect: "duckdb",
            header: false,
            expected_fix: true,
            expected_text: " || ",
        },
        LiteralLimitTestCase {
            description: "MySQL operator is OR",
            sql: "SELECT 'pending shipped'",
            dialect: "mysql",
            header: false,
            expected_fix: true,
            expected_text: "CONCAT(",
        },
        LiteralLimitTestCase {
            description: "T-SQL uses plus",
            sql: "SELECT 'pending shipped'",
            dialect: "tsql",
            header: false,
            expected_fix: true,
            expected_text: " + ",
        },
        LiteralLimitTestCase {
            description: "unsupported concatenation",
            sql: "SELECT 'pending shipped'",
            dialect: "clickhouse",
            header: false,
            expected_fix: false,
            expected_text: "No proven safe",
        },
        LiteralLimitTestCase {
            description: "dollar quoted",
            sql: "SELECT $$pending shipped$$",
            dialect: "postgres",
            header: false,
            expected_fix: false,
            expected_text: "Dollar-quoted",
        },
        LiteralLimitTestCase {
            description: "escape string",
            sql: "SELECT E'pending shipped'",
            dialect: "postgres",
            header: false,
            expected_fix: false,
            expected_text: "escape",
        },
        LiteralLimitTestCase {
            description: "raw string",
            sql: "SELECT r'pending shipped'",
            dialect: "bigquery",
            header: false,
            expected_fix: false,
            expected_text: "raw",
        },
        LiteralLimitTestCase {
            description: "typed string",
            sql: "SELECT DATE '2026-01-01'",
            dialect: "duckdb",
            header: false,
            expected_fix: false,
            expected_text: "Typed literals",
        },
        LiteralLimitTestCase {
            description: "constant-only position",
            sql: "COMMENT ON TABLE orders IS 'pending shipped'",
            dialect: "postgres",
            header: false,
            expected_fix: false,
            expected_text: "constant token",
        },
        LiteralLimitTestCase {
            description: "MODEL header",
            sql: "MODEL (description 'pending shipped')",
            dialect: "duckdb",
            header: true,
            expected_fix: false,
            expected_text: "header strings",
        },
        LiteralLimitTestCase {
            description: "quoted MODEL header",
            sql: "MODEL (description \"pending shipped\")",
            dialect: "duckdb",
            header: true,
            expected_fix: false,
            expected_text: "header strings",
        },
        LiteralLimitTestCase {
            description: "doubled quotes",
            sql: "SELECT 'pending customer''s shipment'",
            dialect: "duckdb",
            header: false,
            expected_fix: false,
            expected_text: "doubled quotes",
        },
        LiteralLimitTestCase {
            description: "backslash escape",
            sql: "SELECT 'pending\\d shipped'",
            dialect: "duckdb",
            header: false,
            expected_fix: false,
            expected_text: "escape sequences",
        },
    ];
    for test_case in test_cases {
        let response = lint_json(&json!({"version":1,"sql":test_case.sql,"dialect":test_case.dialect,"enabled_rules":["SQBRSQL044"],"max_literal_length":8,"header_literals":test_case.header}).to_string())?;
        let payload: Value = serde_json::from_str(&response).map_err(|error| error.to_string())?;
        let diagnostic = &payload["diagnostics"][0];
        assert_eq!(
            diagnostic["code"], "SQBRSQL044",
            "{}",
            test_case.description
        );
        assert_eq!(
            diagnostic.get("fix").is_some(),
            test_case.expected_fix,
            "{}",
            test_case.description
        );
        assert!(
            diagnostic.to_string().contains(test_case.expected_text),
            "{}: {}",
            test_case.description,
            diagnostic
        );
    }
    Ok(())
}
