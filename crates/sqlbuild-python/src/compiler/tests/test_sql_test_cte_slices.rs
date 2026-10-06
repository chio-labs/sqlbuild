use crate::compiler::_helpers::sql_tests::cte_slices::{SliceDialect, split_top_level_with};
use crate::compiler::tests::test_types::CteSliceTestCase;
use crate::sql_scan::models::Unclosed;

#[test]
fn given_leading_with_queries_when_splitting_then_authored_slices_or_none_are_returned() {
    let test_cases = [
        CteSliceTestCase {
            description: "plain CTEs keep their exact authored bodies",
            dialect: "duckdb",
            sql: "WITH a AS (SELECT 1 AS id),\n  b AS ( SELECT id FROM a )\nSELECT * FROM b",
            expected_slices: Ok(Some((
                vec![("a", "SELECT 1 AS id"), ("b", " SELECT id FROM a ")],
                "SELECT * FROM b",
            ))),
        },
        CteSliceTestCase {
            description: "quotes, comments and dollar quotes hide parentheses",
            dialect: "snowflake",
            sql: "-- lead\nWITH \"A\" AS (SELECT ')' AS x /* ) */, $$ ) $$ AS y -- )\n) SELECT * FROM \"A\"",
            expected_slices: Ok(Some((
                vec![("\"A\"", "SELECT ')' AS x /* ) */, $$ ) $$ AS y -- )\n")],
                "SELECT * FROM \"A\"",
            ))),
        },
        CteSliceTestCase {
            description: "nested WITH stays inside its CTE body",
            dialect: "duckdb",
            sql: "WITH outer_rows AS (WITH inner_rows AS (SELECT 1 AS id) SELECT id FROM inner_rows) SELECT id FROM outer_rows",
            expected_slices: Ok(Some((
                vec![(
                    "outer_rows",
                    "WITH inner_rows AS (SELECT 1 AS id) SELECT id FROM inner_rows",
                )],
                "SELECT id FROM outer_rows",
            ))),
        },
        CteSliceTestCase {
            description: "column lists stay in the header",
            dialect: "postgres",
            sql: "WITH totals (order_id, amount) AS (SELECT 1, 2) SELECT * FROM totals",
            expected_slices: Ok(Some((
                vec![("totals (order_id, amount)", "SELECT 1, 2")],
                "SELECT * FROM totals",
            ))),
        },
        CteSliceTestCase {
            description: "comments between CTEs and before the body are kept with the body",
            dialect: "duckdb",
            sql: "WITH a AS (SELECT 1 AS id) /* c */ , b AS (SELECT 2 AS id)\n-- body\nSELECT * FROM a, b",
            expected_slices: Ok(Some((
                vec![("a", "SELECT 1 AS id"), ("b", "SELECT 2 AS id")],
                "-- body\nSELECT * FROM a, b",
            ))),
        },
        CteSliceTestCase {
            description: "BigQuery backslash escapes and backtick names",
            dialect: "bigquery",
            sql: "WITH `rows` AS (SELECT 'it\\'s )' AS note) SELECT * FROM `rows`",
            expected_slices: Ok(Some((
                vec![("`rows`", "SELECT 'it\\'s )' AS note")],
                "SELECT * FROM `rows`",
            ))),
        },
        CteSliceTestCase {
            description: "T-SQL bracket identifiers hide parentheses",
            dialect: "tsql",
            sql: "WITH [odd (name]]] AS (SELECT 1 AS [x)]) SELECT * FROM [odd (name]]]",
            expected_slices: Ok(Some((
                vec![("[odd (name]]]", "SELECT 1 AS [x)]")],
                "SELECT * FROM [odd (name]]]",
            ))),
        },
        CteSliceTestCase {
            description: "recursive WITH is not lifted",
            dialect: "duckdb",
            sql: "WITH RECURSIVE r AS (SELECT 1) SELECT * FROM r",
            expected_slices: Ok(None),
        },
        CteSliceTestCase {
            description: "materialized CTEs are not lifted",
            dialect: "postgres",
            sql: "WITH r AS MATERIALIZED (SELECT 1) SELECT * FROM r",
            expected_slices: Ok(None),
        },
        CteSliceTestCase {
            description: "unbalanced parentheses report the unclosed parenthesis",
            dialect: "duckdb",
            sql: "WITH r AS (SELECT (1) SELECT * FROM r",
            expected_slices: Err(Unclosed::Parenthesis),
        },
        CteSliceTestCase {
            description: "a WITH without a following statement is not lifted",
            dialect: "duckdb",
            sql: "WITH r AS (SELECT 1)",
            expected_slices: Ok(None),
        },
        CteSliceTestCase {
            description: "queries without a leading WITH are not split",
            dialect: "duckdb",
            sql: "SELECT 1 AS withdrawn",
            expected_slices: Ok(None),
        },
    ];

    for test_case in test_cases {
        let actual =
            split_top_level_with(test_case.sql, SliceDialect::new(Some(test_case.dialect))).map(
                |split| {
                    split.map(|split| {
                        (
                            split
                                .ctes
                                .iter()
                                .map(|cte| (cte.header, cte.body))
                                .collect::<Vec<_>>(),
                            split.body,
                        )
                    })
                },
            );
        assert_eq!(
            actual, test_case.expected_slices,
            "{}",
            test_case.description
        );
    }
}
