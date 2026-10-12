use crate::sql_test_attachment::main::sql_test_cte_location::sql_test_cte_location;
use crate::sql_test_attachment::models::{CteLocation, PythonTextMatcher};
use crate::sql_test_attachment::tests::test_types::{
    CteLocationTestCase, ReadsWordTestCase, TokensTestCase,
};
use crate::sql_test_attachment::types::SqlTestTextMatcher;

#[test]
fn given_sql_when_listing_identifier_tokens_then_they_match_python_re_and_casefold() {
    let test_cases = [
        TokensTestCase {
            description: "tokens casefold and repeat once, dollar signs included",
            sql: "select Orders, orders, ORDERS from x$y",
            expected_tokens: &["select", "orders", "from", "x$y"],
        },
        TokensTestCase {
            description: "a token starts at an ASCII letter and continues through Unicode word text",
            sql: "caf\u{e9} \u{e9}t\u{e9} _a1 1b",
            expected_tokens: &["caf\u{e9}", "t\u{e9}", "_a1", "b"],
        },
        TokensTestCase {
            description: "sharp s stays distinct from ss and a long s cannot start a token",
            sql: "Stra\u{df}e STRASSE \u{17f}pan",
            expected_tokens: &["stra\u{df}e", "strasse", "pan"],
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            PythonTextMatcher.identifier_tokens(test_case.sql),
            Ok(test_case
                .expected_tokens
                .iter()
                .map(|token| (*token).to_owned())
                .collect::<Vec<String>>()),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_sql_when_searching_a_word_then_ignorecase_and_boundaries_match_python_re() {
    let test_cases = [
        ReadsWordTestCase {
            description: "case is ignored",
            sql: "from orders o",
            word: "ORDERS",
            expected_reads: true,
        },
        ReadsWordTestCase {
            description: "a following word character is a longer word",
            sql: "from orders_x",
            word: "orders",
            expected_reads: false,
        },
        ReadsWordTestCase {
            description: "a preceding dollar sign is part of the word",
            sql: "$orders",
            word: "orders",
            expected_reads: false,
        },
        ReadsWordTestCase {
            description: "long s and the Kelvin sign match their ASCII letters",
            sql: "\u{17f}pan \u{212a}ey",
            word: "key",
            expected_reads: true,
        },
        ReadsWordTestCase {
            description: "a preceding Unicode letter is a longer word",
            sql: "caf\u{e9}orders",
            word: "orders",
            expected_reads: false,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            PythonTextMatcher.reads_word(test_case.sql, test_case.word),
            Ok(test_case.expected_reads),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_helper_problems_when_locating_then_spans_match_the_python_locator() {
    let test_cases = [
        CteLocationTestCase {
            description: "the call inside the CTE is located",
            contents: "WITH orders AS (SELECT * FROM __ref(\"orders\"))\nSELECT 1",
            sql_body: "WITH orders",
            cte_name: "orders",
            call: Some("__ref(\"orders\")"),
            expected_location: (1, 31, 1, 46),
        },
        CteLocationTestCase {
            description: "a quoted name, a line break and a non-breaking space locate the header",
            contents: "WITH \"Orders\"\n  as\u{a0}(select 1)\nSELECT 1",
            sql_body: "WITH",
            cte_name: "orders",
            call: None,
            expected_location: (1, 7, 1, 13),
        },
        CteLocationTestCase {
            description: "a missing block and CTE fall back to the file start",
            contents: "caf\u{e9}\nWITH b AS (1)",
            sql_body: "missing body",
            cte_name: "orders",
            call: None,
            expected_location: (1, 1, 1, 1),
        },
        CteLocationTestCase {
            description: "a call not found keeps the CTE name",
            contents: "WITH orders AS(select 1)",
            sql_body: "WITH",
            cte_name: "orders",
            call: Some("nothing"),
            expected_location: (1, 6, 1, 12),
        },
    ];
    for test_case in test_cases {
        let location: CteLocation = sql_test_cte_location(
            test_case.contents,
            test_case.sql_body,
            test_case.cte_name,
            test_case.call,
        );

        assert_eq!(
            (
                location.line,
                location.column,
                location.end_line,
                location.end_column
            ),
            test_case.expected_location,
            "{}",
            test_case.description
        );
    }
}
