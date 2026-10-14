use crate::lint_text::main::simplify_fixture_nulls::simplify_fixture_nulls;
use crate::lint_text::tests::test_types::FixtureFormattingTestCase;

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
