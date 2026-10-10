use crate::audits::_helpers::parameters::RenderStop;
use crate::audits::tests::helpers::rendered_sql;
use crate::audits::tests::test_types::ParameterizedSqlTestCase;

#[test]
fn given_parameterized_sql_when_rendering_then_python_text_is_returned() {
    let test_cases = [
        ParameterizedSqlTestCase {
            description: "raw and quoted parameters: lists joined, only text quoted, quotes doubled",
            sql: "WHERE @column IN (@'values') AND x = @values",
            expected_sql: Ok(
                "WHERE status IN ('it''s', 2, NULL, TRUE) AND x = it's, 2, NULL, TRUE",
            ),
        },
        ParameterizedSqlTestCase {
            description: "macro calls, doubled @ and runtime placeholders are left alone",
            sql: "@column (x) @@column @@@column @column(y)",
            expected_sql: Ok("@column (x) @@column @@@column @column(y)"),
        },
        ParameterizedSqlTestCase {
            description: "the first missing argument stops rendering with its name",
            sql: "WHERE @column = @missing AND @'other'",
            expected_sql: Err(RenderStop::MissingArgument("missing".to_owned())),
        },
        ParameterizedSqlTestCase {
            description: "Unicode whitespace before a parenthesis makes a macro call",
            sql: "WHERE @column\u{a0}( AND @column\u{e9}",
            expected_sql: Ok("WHERE @column\u{a0}( AND status\u{e9}"),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            rendered_sql(test_case.sql),
            test_case.expected_sql.map(str::to_owned),
            "{}",
            test_case.description
        );
    }
}
