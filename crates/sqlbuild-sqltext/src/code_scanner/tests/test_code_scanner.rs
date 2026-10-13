use crate::code_scanner::main::code_scanner::code_scanner;
use crate::code_scanner::main::scanner_matching_paren::scanner_matching_paren;
use crate::code_scanner::main::scanner_non_code_end::scanner_non_code_end;
use crate::code_scanner::tests::helpers::dialect;
use crate::code_scanner::tests::test_types::{MatchingParenTestCase, NonCodeEndTestCase};
use crate::sql_scan::models::Unclosed;

/// Expectations recorded from the Python `sql_analysis` scanners this replaces.
#[test]
fn given_sql_when_finding_non_code_end_then_matches_python_offsets() {
    let test_cases = [
        NonCodeEndTestCase {
            description: "generic backticks end at the first closing backtick",
            sql: "`a``b` x",
            syntax: None,
            index: 0,
            expected_end: Ok(Some(3)),
        },
        NonCodeEndTestCase {
            description: "dialect backticks double to escape",
            sql: "`a``b` x",
            syntax: Some(dialect()),
            index: 0,
            expected_end: Ok(Some(6)),
        },
        NonCodeEndTestCase {
            description: "a generic lone dollar is one character",
            sql: "$1 x",
            syntax: None,
            index: 0,
            expected_end: Ok(Some(1)),
        },
        NonCodeEndTestCase {
            description: "a dialect lone dollar is code",
            sql: "$1 x",
            syntax: Some(dialect()),
            index: 0,
            expected_end: Ok(None),
        },
        NonCodeEndTestCase {
            description: "offsets count code points",
            sql: "é 'naïve' x",
            syntax: None,
            index: 2,
            expected_end: Ok(Some(9)),
        },
        NonCodeEndTestCase {
            description: "a dialect line comment prefix",
            sql: "é # note\nx",
            syntax: Some(dialect()),
            index: 2,
            expected_end: Ok(Some(9)),
        },
        NonCodeEndTestCase {
            description: "nested block comments",
            sql: "/* a /* b */ c */ x",
            syntax: Some(dialect()),
            index: 0,
            expected_end: Ok(Some(17)),
        },
        NonCodeEndTestCase {
            description: "generic block comments do not nest",
            sql: "/* a /* b */ c */ x",
            syntax: None,
            index: 0,
            expected_end: Ok(Some(12)),
        },
        NonCodeEndTestCase {
            description: "an unclosed dollar quote",
            sql: "$tag$ never",
            syntax: None,
            index: 0,
            expected_end: Err(Unclosed::Quote),
        },
        NonCodeEndTestCase {
            description: "an unclosed block comment",
            sql: "/* never",
            syntax: Some(dialect()),
            index: 0,
            expected_end: Err(Unclosed::BlockComment),
        },
        NonCodeEndTestCase {
            description: "code",
            sql: "select 1",
            syntax: None,
            index: 0,
            expected_end: Ok(None),
        },
    ];
    for test_case in test_cases {
        let scanner = code_scanner(test_case.sql, test_case.syntax);
        assert_eq!(
            scanner_non_code_end(&scanner, test_case.index),
            test_case.expected_end,
            "{}",
            test_case.description
        );
    }
}

/// Expectations recorded from the Python `find_matching_paren` this replaces.
#[test]
fn given_open_parenthesis_when_matching_then_skips_text_and_comments() {
    let test_cases = [
        MatchingParenTestCase {
            description: "nested parentheses",
            sql: "f(a, (b), c) x",
            open: 1,
            expected_close: Ok(11),
        },
        MatchingParenTestCase {
            description: "parentheses in quotes, comments and backticks",
            sql: "f(')', `)`, -- )\n /* ) */ $$)$$) x",
            open: 1,
            expected_close: Ok(31),
        },
        MatchingParenTestCase {
            description: "code point offsets",
            sql: "ééf('é)') x",
            open: 3,
            expected_close: Ok(8),
        },
        MatchingParenTestCase {
            description: "an unclosed parenthesis",
            sql: "f(a",
            open: 1,
            expected_close: Err(Unclosed::Parenthesis),
        },
    ];
    for test_case in test_cases {
        let scanner = code_scanner(test_case.sql, None);
        assert_eq!(
            scanner_matching_paren(&scanner, test_case.open),
            test_case.expected_close,
            "{}",
            test_case.description
        );
    }
}
