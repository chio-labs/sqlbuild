use crate::audits::tests::helpers::rendered_sql;
use crate::audits::tests::test_types::ParameterizedSqlTestCase;

#[test]
fn given_parameterized_sql_when_rendering_then_python_text_is_returned() {
    let test_cases = [
        ParameterizedSqlTestCase {
            description: "raw and quoted parameters: lists joined, only text quoted, quotes doubled",
            sql: "WHERE @column IN (@'values') AND x = @values",
            reject_unused: false,
            expected_sql: Some(
                "WHERE status IN ('it''s', 2, NULL, TRUE) AND x = it's, 2, NULL, TRUE",
            ),
        },
        ParameterizedSqlTestCase {
            description: "macro calls, doubled @ and runtime placeholders are left alone",
            sql: "@column (x) @@column @@@column @column(y)",
            reject_unused: false,
            expected_sql: Some("@column (x) @@column @@@column @column(y)"),
        },
        ParameterizedSqlTestCase {
            description: "a missing argument defers so Python raises",
            sql: "WHERE @missing",
            reject_unused: false,
            expected_sql: None,
        },
        ParameterizedSqlTestCase {
            description: "an unused argument defers when unused arguments are rejected",
            sql: "WHERE @column",
            reject_unused: true,
            expected_sql: None,
        },
        ParameterizedSqlTestCase {
            description: "a non-ASCII character after a name defers to Python's whitespace",
            sql: "WHERE @column\u{a0}(",
            reject_unused: false,
            expected_sql: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            rendered_sql(test_case.sql, test_case.reject_unused).as_deref(),
            test_case.expected_sql,
            "{}",
            test_case.description
        );
    }
}
