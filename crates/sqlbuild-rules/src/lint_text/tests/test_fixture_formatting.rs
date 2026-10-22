use crate::lint_text::_helpers::fixture_formatting::simplify_fixture_nulls;
use crate::lint_text::main::format_fixture_blocks::format_fixture_blocks;
use crate::lint_text::models::{FixtureFormatBlock, FixtureFormatRelation};
use crate::lint_text::tests::test_types::FixtureBlockTestCase;
use crate::lint_text::tests::test_types::FixtureFormattingTestCase;
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;
use std::collections::HashMap;

#[test]
fn given_authored_blocks_when_formatting_then_only_unique_model_fixtures_change()
-> Result<(), regex::Error> {
    let relations = HashMap::from([(
        "__ref__orders".to_owned(),
        FixtureFormatRelation {
            columns: vec![("id".into(), Some("INTEGER".into()), Some(true))],
        },
    )]);
    let test_cases = [
        FixtureBlockTestCase {
            description: "unique fixture body changes",
            sql: "WITH __ref__orders AS (SELECT CAST(NULL AS INTEGER) AS id WHERE FALSE) SELECT 1",
            model_mode: true,
            expected_sql: Some("WITH __ref__orders AS (SELECT * FROM __empty_fixture()) SELECT 1"),
        },
        FixtureBlockTestCase {
            description: "ambiguous duplicate bodies are retained",
            sql: "WITH __ref__orders AS (SELECT CAST(NULL AS INTEGER) AS id WHERE FALSE), other AS (SELECT CAST(NULL AS INTEGER) AS id WHERE FALSE) SELECT 1",
            model_mode: true,
            expected_sql: None,
        },
        FixtureBlockTestCase {
            description: "expected output is not an input fixture",
            sql: "WITH __expected__orders AS (SELECT CAST(NULL AS INTEGER) AS id WHERE FALSE) SELECT 1",
            model_mode: true,
            expected_sql: None,
        },
        FixtureBlockTestCase {
            description: "macro-bearing blocks are retained",
            sql: "WITH __ref__orders AS (SELECT CAST(NULL AS INTEGER) AS id WHERE FALSE) SELECT @value()",
            model_mode: true,
            expected_sql: None,
        },
        FixtureBlockTestCase {
            description: "non-model blocks are retained",
            sql: "WITH __ref__orders AS (SELECT CAST(NULL AS INTEGER) AS id WHERE FALSE) SELECT 1",
            model_mode: false,
            expected_sql: None,
        },
    ];
    for test_case in test_cases {
        let blocks = [FixtureFormatBlock {
            sql_body: test_case.sql.into(),
            model_mode: test_case.model_mode,
        }];
        assert_eq!(
            format_fixture_blocks(
                (test_case.sql, "test_orders.sql"),
                &blocks,
                &relations,
                &LexicalSyntax::default()
            )?
            .as_deref(),
            test_case.expected_sql,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_authoritative_columns_when_simplifying_then_preserves_schema_order()
-> Result<(), regex::Error> {
    let columns: Vec<(String, Option<String>, Option<bool>)> = vec![
        ("order_id".into(), Some("INTEGER".into()), Some(false)),
        ("amount".into(), Some("DECIMAL(12, 3)".into()), Some(true)),
    ];
    let test_cases = [
        FixtureFormattingTestCase {
            description: "nullable trailing column",
            sql: "SELECT\n  1 AS order_id,\n  CAST(NULL AS DECIMAL(12, 3)) AS amount\nWHERE TRUE",
            columns: columns.clone(),
            expected_sql: "SELECT\n  1 AS order_id\nWHERE TRUE",
        },
        FixtureFormattingTestCase {
            description: "out-of-order projection retained",
            sql: "SELECT\n  CAST(NULL AS DECIMAL(12, 3)) AS amount,\n  1 AS order_id",
            columns: columns.clone(),
            expected_sql: "SELECT\n  CAST(NULL AS DECIMAL(12, 3)) AS amount,\n  1 AS order_id",
        },
        FixtureFormattingTestCase {
            description: "empty fixture with decimal precision",
            sql: "SELECT CAST(NULL AS INTEGER) AS order_id, CAST(NULL AS DECIMAL(12, 3)) AS amount WHERE FALSE",
            columns: columns.clone(),
            expected_sql: "SELECT * FROM __empty_fixture()",
        },
        FixtureFormattingTestCase {
            description: "non-nullable projection retained",
            sql: "SELECT\n  CAST(NULL AS INTEGER) AS order_id,\n  2 AS amount",
            columns: columns.clone(),
            expected_sql: "SELECT\n  CAST(NULL AS INTEGER) AS order_id,\n  2 AS amount",
        },
        FixtureFormattingTestCase {
            description: "unsupported array spelling retained",
            sql: "SELECT\n  1 AS order_id,\n  CAST(NULL AS INTEGER[]) AS amount",
            columns: columns.clone(),
            expected_sql: "SELECT\n  1 AS order_id,\n  CAST(NULL AS INTEGER[]) AS amount",
        },
        FixtureFormattingTestCase {
            description: "set operation retained",
            sql: "SELECT\n  1 AS order_id,\n  CAST(NULL AS INTEGER) AS amount\nUNION ALL SELECT 2, 3",
            columns: columns.clone(),
            expected_sql: "SELECT\n  1 AS order_id,\n  CAST(NULL AS INTEGER) AS amount\nUNION ALL SELECT 2, 3",
        },
        FixtureFormattingTestCase {
            description: "unicode line boundaries",
            sql: "SELECT\u{2028}  1 AS order_id,\u{2028}  CAST(NULL AS DECIMAL(12, 3)) AS amount",
            columns,
            expected_sql: "SELECT\n  1 AS order_id",
        },
        FixtureFormattingTestCase {
            description: "last duplicate column has unknown type",
            sql: "SELECT\n  1 AS order_id,\n  CAST(NULL AS INTEGER) AS amount",
            columns: vec![
                ("order_id".into(), Some("INTEGER".into()), None),
                ("amount".into(), Some("INTEGER".into()), None),
                ("AMOUNT".into(), None, None),
            ],
            expected_sql: "SELECT\n  1 AS order_id,\n  CAST(NULL AS INTEGER) AS amount",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            simplify_fixture_nulls(test_case.sql, &test_case.columns)?,
            test_case.expected_sql,
            "{}",
            test_case.description
        );
    }
    Ok(())
}
