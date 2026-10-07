use crate::relationship_names::tests::helpers::{dialect_syntax, expected, generic_syntax, names};
use crate::relationship_names::tests::test_types::{ExpectedNamesTestCase, SyntaxTestCase};

#[test]
fn given_sql_test_when_scanning_expected_models_then_names_match_python_or_defer() {
    let test_cases = [
        ExpectedNamesTestCase {
            description: "expected CTEs in authored order after mocks",
            sql: "WITH\n__source__raw AS (SELECT 1),\n__expected__orders AS (SELECT 2),\n\
                  __expected__customers AS (SELECT 3)\nSELECT 1\n",
            expected_names: Some(&["orders", "customers"]),
        },
        ExpectedNamesTestCase {
            description: "comments, column lists, RECURSIVE and an omitted SELECT 1",
            sql: "-- header\n/* note */ with recursive __expected__a (x, y) AS (\n\
                  SELECT ')' AS x, 1 AS y -- )\n)",
            expected_names: Some(&["a"]),
        },
        ExpectedNamesTestCase {
            description: "a terminated ceremonial select with trailing comments",
            sql: "WITH __expected__a AS (SELECT 1) select 1 ; -- done\n",
            expected_names: Some(&["a"]),
        },
        ExpectedNamesTestCase {
            description: "no top-level WITH has no expected models",
            sql: "SELECT 1",
            expected_names: Some(&[]),
        },
        ExpectedNamesTestCase {
            description: "a keyword prefix of an identifier is not WITH",
            sql: "WITHIN AS (SELECT 1)",
            expected_names: Some(&[]),
        },
        ExpectedNamesTestCase {
            description: "non-ASCII inside bodies, strings and comments is opaque",
            sql: "WITH __expected__a AS (SELECT 'caf\u{e9}' AS \"\u{e9}\") -- \u{e9}\nSELECT 1",
            expected_names: Some(&["a"]),
        },
        ExpectedNamesTestCase {
            description: "non-ASCII at a code position defers",
            sql: "WITH __expected__caf\u{e9} AS (SELECT 1) SELECT 1",
            expected_names: None,
        },
        ExpectedNamesTestCase {
            description: "non-ASCII whitespace defers",
            sql: "WITH\u{a0}__expected__a AS (SELECT 1) SELECT 1",
            expected_names: None,
        },
        ExpectedNamesTestCase {
            description: "a non-ASCII character Python upper-cases into a keyword defers",
            sql: "w\u{131}th __expected__a AS (SELECT 1) SELECT 1",
            expected_names: None,
        },
        ExpectedNamesTestCase {
            description: "Python separators count as whitespace",
            sql: "WITH\u{1f}__expected__a AS (SELECT 1)\u{b}SELECT 1",
            expected_names: Some(&["a"]),
        },
        ExpectedNamesTestCase {
            description: "a bare expected prefix defers to Python's error",
            sql: "WITH __expected__ AS (SELECT 1) SELECT 1",
            expected_names: None,
        },
        ExpectedNamesTestCase {
            description: "a duplicate CTE defers to Python's error",
            sql: "WITH a AS (SELECT 1), a AS (SELECT 2) SELECT 1",
            expected_names: None,
        },
        ExpectedNamesTestCase {
            description: "a final statement other than SELECT 1 defers",
            sql: "WITH __expected__a AS (SELECT 1) SELECT 2",
            expected_names: None,
        },
        ExpectedNamesTestCase {
            description: "a missing AS defers",
            sql: "WITH __expected__a (SELECT 1) SELECT 1",
            expected_names: None,
        },
        ExpectedNamesTestCase {
            description: "an unclosed parenthesis defers",
            sql: "WITH __expected__a AS (SELECT (1) SELECT 1",
            expected_names: None,
        },
        ExpectedNamesTestCase {
            description: "an unclosed block comment defers",
            sql: "/* open\nWITH __expected__a AS (SELECT 1)",
            expected_names: None,
        },
        ExpectedNamesTestCase {
            description: "a quoted CTE name defers to Python's error",
            sql: "WITH \"__expected__a\" AS (SELECT 1) SELECT 1",
            expected_names: None,
        },
        ExpectedNamesTestCase {
            description: "a dollar sign at a code position defers",
            sql: "WITH __expected__a AS (SELECT 1) $x",
            expected_names: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            names(test_case.sql, &generic_syntax()),
            expected(test_case.expected_names),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_dialect_rules_when_scanning_expected_models_then_comments_and_quotes_follow_them() {
    let test_cases = [
        SyntaxTestCase {
            description: "hash line comments hide a closing parenthesis",
            backslash_escape_quotes: &[],
            nested_block_comments: false,
            line_comment_prefixes: &["--", "#"],
            sql: "WITH __expected__a AS (SELECT 1 # )\n) SELECT 1",
            expected_names: Some(&["a"]),
        },
        SyntaxTestCase {
            description: "nested block comments close at the outer delimiter",
            backslash_escape_quotes: &[],
            nested_block_comments: true,
            line_comment_prefixes: &["--"],
            sql: "/* a /* b */ ) */ WITH __expected__a AS (SELECT 1) SELECT 1",
            expected_names: Some(&["a"]),
        },
        SyntaxTestCase {
            description: "backslash-escaped quotes keep the string open",
            backslash_escape_quotes: &["'"],
            nested_block_comments: false,
            line_comment_prefixes: &["--"],
            sql: "WITH __expected__a AS (SELECT 'it\\')' AS x) SELECT 1",
            expected_names: Some(&["a"]),
        },
        SyntaxTestCase {
            description: "a line comment prefix Python's matcher never looks for defers",
            backslash_escape_quotes: &[],
            nested_block_comments: false,
            line_comment_prefixes: &["--", ";;"],
            sql: "WITH __expected__a AS (SELECT 1) SELECT 1",
            expected_names: None,
        },
    ];

    for test_case in test_cases {
        let syntax = dialect_syntax(&test_case);
        assert_eq!(
            names(test_case.sql, &syntax),
            expected(test_case.expected_names),
            "{}",
            test_case.description
        );
    }
}
