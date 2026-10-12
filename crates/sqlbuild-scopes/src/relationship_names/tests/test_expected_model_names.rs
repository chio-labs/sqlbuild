use crate::relationship_names::models::TopLevelCtes;
use crate::relationship_names::tests::helpers::{
    ctes, dialect_syntax, failed, generic_syntax, names, scanned, scanned_ctes, scenario_names,
};
use crate::relationship_names::tests::test_types::{
    ExpectedNamesTestCase, ScenarioNamesTestCase, SyntaxTestCase, TopLevelCtesTestCase,
};

#[test]
fn given_sql_test_when_scanning_expected_models_then_names_and_errors_match_python_or_defer() {
    let test_cases = [
        ExpectedNamesTestCase {
            description: "expected CTEs in authored order after mocks",
            sql: "WITH\n__source__raw AS (SELECT 1),\n__expected__orders AS (SELECT 2),\n\
                  __expected__customers AS (SELECT 3)\nSELECT 1\n",
            expected_outcome: scanned(&["orders", "customers"]),
        },
        ExpectedNamesTestCase {
            description: "comments, column lists, RECURSIVE and an omitted SELECT 1",
            sql: "-- header\n/* note */ with recursive __expected__a (x, y) AS (\n\
                  SELECT ')' AS x, 1 AS y -- )\n)",
            expected_outcome: scanned(&["a"]),
        },
        ExpectedNamesTestCase {
            description: "a terminated ceremonial select with trailing comments",
            sql: "WITH __expected__a AS (SELECT 1) select 1 ; -- done\n",
            expected_outcome: scanned(&["a"]),
        },
        ExpectedNamesTestCase {
            description: "no top-level WITH has no expected models",
            sql: "SELECT 1",
            expected_outcome: scanned(&[]),
        },
        ExpectedNamesTestCase {
            description: "a keyword prefix of an identifier is not WITH",
            sql: "WITHIN AS (SELECT 1)",
            expected_outcome: scanned(&[]),
        },
        ExpectedNamesTestCase {
            description: "non-ASCII inside bodies, strings and comments is opaque",
            sql: "WITH __expected__a AS (SELECT 'caf\u{e9}' AS \"\u{e9}\") -- \u{e9}\nSELECT 1",
            expected_outcome: scanned(&["a"]),
        },
        ExpectedNamesTestCase {
            description: "non-ASCII letters continue a CTE name",
            sql: "WITH __expected__caf\u{e9} AS (SELECT 1) SELECT 1",
            expected_outcome: scanned(&["caf\u{e9}"]),
        },
        ExpectedNamesTestCase {
            description: "non-ASCII whitespace is skipped",
            sql: "WITH\u{a0}__expected__a AS (SELECT 1) SELECT 1",
            expected_outcome: scanned(&["a"]),
        },
        ExpectedNamesTestCase {
            description: "a non-ASCII character that upper-cases into a keyword reads as it",
            sql: "w\u{131}th __expected__a AS (SELECT 1) SELECT 1",
            expected_outcome: scanned(&["a"]),
        },
        ExpectedNamesTestCase {
            description: "Python separators count as whitespace",
            sql: "WITH\u{1f}__expected__a AS (SELECT 1)\u{b}SELECT 1",
            expected_outcome: scanned(&["a"]),
        },
        ExpectedNamesTestCase {
            description: "a bare expected prefix raises Python's error",
            sql: "WITH __expected__ AS (SELECT 1) SELECT 1",
            expected_outcome: failed(
                "SQL test 'tests/unit/test_orders.sql' must use __expected__<model> to identify a target",
            ),
        },
        ExpectedNamesTestCase {
            description: "a duplicate CTE raises Python's error",
            sql: "WITH a AS (SELECT 1), a AS (SELECT 2) SELECT 1",
            expected_outcome: failed(
                "SQL test 'tests/unit/test_orders.sql' defines duplicate CTE 'a'",
            ),
        },
        ExpectedNamesTestCase {
            description: "a final statement other than SELECT 1 raises Python's error",
            sql: "WITH __expected__a AS (SELECT 1) SELECT 2",
            expected_outcome: failed(
                "SQL test 'tests/unit/test_orders.sql' must end after its CTEs; only an optional ceremonial top-level `SELECT 1` may follow them",
            ),
        },
        ExpectedNamesTestCase {
            description: "a missing AS raises Python's error",
            sql: "WITH __expected__a (SELECT 1) SELECT 1",
            expected_outcome: failed("SQL test 'tests/unit/test_orders.sql' expected keyword AS"),
        },
        ExpectedNamesTestCase {
            description: "an unclosed parenthesis raises Python's error",
            sql: "WITH __expected__a AS (SELECT (1) SELECT 1",
            expected_outcome: failed("SQL test contains an unclosed parenthesis"),
        },
        ExpectedNamesTestCase {
            description: "an unclosed block comment raises Python's error",
            sql: "/* open\nWITH __expected__a AS (SELECT 1)",
            expected_outcome: failed("SQL test contains an unclosed block comment"),
        },
        ExpectedNamesTestCase {
            description: "a quoted CTE name raises Python's error",
            sql: "WITH \"__expected__a\" AS (SELECT 1) SELECT 1",
            expected_outcome: failed("SQL test 'tests/unit/test_orders.sql' expected a CTE name"),
        },
        ExpectedNamesTestCase {
            description: "a missing CTE body raises Python's error",
            sql: "WITH __expected__a AS SELECT 1",
            expected_outcome: failed(
                "SQL test 'tests/unit/test_orders.sql' CTE '__expected__a' must use AS (...)",
            ),
        },
        ExpectedNamesTestCase {
            description: "a materialization hint raises Python's error",
            sql: "WITH __expected__a AS not  MATERIALIZED (SELECT 1) SELECT 1",
            expected_outcome: failed(
                "SQL test 'tests/unit/test_orders.sql' CTE '__expected__a' must not use AS NOT \
                 MATERIALIZED; materialization hints are not supported in SQL test CTEs",
            ),
        },
        ExpectedNamesTestCase {
            description: "an unclosed quote inside a body raises Python's error",
            sql: "WITH __expected__a AS (SELECT 'open) SELECT 1",
            expected_outcome: failed("SQL test contains an unclosed quoted string"),
        },
        ExpectedNamesTestCase {
            description: "a non-ASCII letter starts a CTE name",
            sql: "WITH __expected__a AS (SELECT 1), \u{e9}x AS (SELECT 2) SELECT 1",
            expected_outcome: scanned(&["a"]),
        },
        ExpectedNamesTestCase {
            description: "a non-ASCII symbol is not a CTE name",
            sql: "WITH __expected__a AS (SELECT 1), \u{b7}x AS (SELECT 2) SELECT 1",
            expected_outcome: failed("SQL test 'tests/unit/test_orders.sql' expected a CTE name"),
        },
        ExpectedNamesTestCase {
            description: "a dollar sign after the CTEs raises Python's trailing statement error",
            sql: "WITH __expected__a AS (SELECT 1) $x",
            expected_outcome: failed(
                "SQL test 'tests/unit/test_orders.sql' must end after its CTEs; only an optional ceremonial top-level `SELECT 1` may follow them",
            ),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            names(test_case.sql, &generic_syntax()),
            test_case.expected_outcome,
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
            expected_outcome: scanned(&["a"]),
        },
        SyntaxTestCase {
            description: "nested block comments close at the outer delimiter",
            backslash_escape_quotes: &[],
            nested_block_comments: true,
            line_comment_prefixes: &["--"],
            sql: "/* a /* b */ ) */ WITH __expected__a AS (SELECT 1) SELECT 1",
            expected_outcome: scanned(&["a"]),
        },
        SyntaxTestCase {
            description: "backslash-escaped quotes keep the string open",
            backslash_escape_quotes: &["'"],
            nested_block_comments: false,
            line_comment_prefixes: &["--"],
            sql: "WITH __expected__a AS (SELECT 'it\\')' AS x) SELECT 1",
            expected_outcome: scanned(&["a"]),
        },
    ];

    for test_case in test_cases {
        let syntax = dialect_syntax(&test_case);
        assert_eq!(
            names(test_case.sql, &syntax),
            test_case.expected_outcome,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_scenario_when_scanning_expected_models_then_errors_name_the_scenario() {
    let test_cases = [
        ScenarioNamesTestCase {
            description: "expected CTEs after fixtures",
            sql: "WITH __source__raw AS (SELECT 1), __expected__orders AS (SELECT 2) SELECT 1",
            expected_outcome: scanned(&["orders"]),
        },
        ScenarioNamesTestCase {
            description: "a bare expected prefix names the scenario",
            sql: "WITH __source__raw AS (SELECT 1), __expected__ AS (SELECT 2) SELECT 1",
            expected_outcome: failed(
                "SQL scenario 'tests/scenarios/orders.sql' must use __expected__<model> to \
                 identify a target",
            ),
        },
        ScenarioNamesTestCase {
            description: "an unclosed parenthesis names the scenario context",
            sql: "WITH __source__raw AS (SELECT 1",
            expected_outcome: failed("SQL scenario contains an unclosed parenthesis"),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            scenario_names(test_case.sql),
            test_case.expected_outcome,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_sql_text_when_scanning_top_level_ctes_then_bodies_and_errors_match_python() {
    let test_cases = [
        TopLevelCtesTestCase {
            description: "stripped bodies in authored order",
            sql: "WITH helper AS (\n  SELECT 1 AS id\n), __macro_actual__ AS ( SELECT @tidy(id) FROM \
                  helper ) SELECT 1",
            expected_outcome: scanned_ctes(&[
                ("helper", "SELECT 1 AS id"),
                ("__macro_actual__", "SELECT @tidy(id) FROM helper"),
            ]),
        },
        TopLevelCtesTestCase {
            description: "non-ASCII inside a body is kept and stripped by Python's rules",
            sql: "WITH a AS (\u{3000}SELECT 'caf\u{e9}'\u{a0})",
            expected_outcome: scanned_ctes(&[("a", "SELECT 'caf\u{e9}'")]),
        },
        TopLevelCtesTestCase {
            description: "a missing WITH names the test requirement",
            sql: "SELECT 1",
            expected_outcome: TopLevelCtes::Failed(
                "SQL test 'tests/unit/test_orders.sql' must declare mock CTEs and one \
                 __expected__<model> CTE in a top-level WITH clause"
                    .to_owned(),
            ),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            ctes(test_case.sql),
            test_case.expected_outcome,
            "{}",
            test_case.description
        );
    }
}
