use crate::sql_scan::main::matching_paren::matching_paren;
use crate::sql_scan::main::non_code_end::non_code_end;
use crate::sql_scan::models::QuotePolicy;
use crate::sql_scan::models::Unclosed;
use crate::sql_scan::tests::helpers::{dispatch_truncation_cases, ordinary_byte_cases};
use crate::sql_scan::tests::test_types::{
    DispatchInputTestCase, MatchingParenPolicyTestCase, NonCodeEndTestCase,
};

const QUOTES_ONLY: QuotePolicy = QuotePolicy {
    backtick_identifiers: false,
    single_quote_backslash_escapes: false,
    double_quote_backslash_escapes: false,
    dollar_quotes: false,
};

const BACKSLASH_ONLY: QuotePolicy = QuotePolicy {
    backtick_identifiers: false,
    single_quote_backslash_escapes: true,
    double_quote_backslash_escapes: false,
    dollar_quotes: false,
};

#[test]
fn given_every_truncation_and_policy_when_dispatching_then_matches_comment_first_scanning() {
    let test_cases = [
        DispatchInputTestCase {
            description: "ordinary code and non-nesting comments",
            expected_cases: dispatch_truncation_cases,
            sql: b"SELECT orders.id - 1 / 2; -- note\r\n/* outer /* inner */ tail */",
        },
        DispatchInputTestCase {
            description: "multibyte text and doubled quotes",
            expected_cases: dispatch_truncation_cases,
            sql: "SELECT 'é''ü', \"ñ\"\"名\", `名``é`, $$ ' -- /* ü $$".as_bytes(),
        },
        DispatchInputTestCase {
            description: "backslash escapes and tagged dollar quotes",
            expected_cases: dispatch_truncation_cases,
            sql: br#"'a\'b' "c\"d" `e\`f` $tag_2$ /* -- ' " $other$ $tag_2$"#,
        },
        DispatchInputTestCase {
            description: "invalid dollar tags and unclosed quotes",
            expected_cases: dispatch_truncation_cases,
            sql: b"$ $1 $1$ $tag $tag$unterminated $$unterminated",
        },
        DispatchInputTestCase {
            description: "dollar tag word boundaries",
            expected_cases: dispatch_truncation_cases,
            sql: "word$tag$ é$tag$ _$$ $tag$body$tag$".as_bytes(),
        },
        DispatchInputTestCase {
            description: "truncated opening delimiters",
            expected_cases: dispatch_truncation_cases,
            sql: b"- / -- /* ' \" ` \\",
        },
    ];
    for test_case in test_cases {
        for sample in (test_case.expected_cases)(test_case.sql) {
            assert_eq!(
                non_code_end(&sample.sql, sample.index, sample.policy),
                sample.expected_end,
                "{}: {}",
                test_case.description,
                sample.description,
            );
        }
    }
}

#[test]
fn given_non_opening_bytes_when_dispatching_then_returns_no_boundary() {
    let test_cases = [
        DispatchInputTestCase {
            description: "before a line comment",
            expected_cases: ordinary_byte_cases,
            sql: b"--",
        },
        DispatchInputTestCase {
            description: "before a block comment",
            expected_cases: ordinary_byte_cases,
            sql: b"/*",
        },
        DispatchInputTestCase {
            description: "before a single quote",
            expected_cases: ordinary_byte_cases,
            sql: b"'",
        },
        DispatchInputTestCase {
            description: "before a double quote",
            expected_cases: ordinary_byte_cases,
            sql: b"\"",
        },
        DispatchInputTestCase {
            description: "before a backtick",
            expected_cases: ordinary_byte_cases,
            sql: b"`",
        },
        DispatchInputTestCase {
            description: "before a dollar quote",
            expected_cases: ordinary_byte_cases,
            sql: b"$$",
        },
    ];
    for test_case in test_cases {
        for sample in (test_case.expected_cases)(test_case.sql) {
            assert_eq!(
                non_code_end(&sample.sql, sample.index, sample.policy),
                sample.expected_end,
                "{}: {}",
                test_case.description,
                sample.description,
            );
        }
    }
}

#[test]
fn given_quote_policies_when_matching_parentheses_then_policy_decides_quote_boundaries() {
    let test_cases = [
        MatchingParenPolicyTestCase {
            description: "compiler policy skips backtick identifiers",
            sql: "(`a)b` x) y",
            policy: QuotePolicy::COMPILER,
            expected_close: Ok(8),
        },
        MatchingParenPolicyTestCase {
            description: "quotes-only policy treats backticks as code",
            sql: "(`a)b` x) y",
            policy: QUOTES_ONLY,
            expected_close: Ok(3),
        },
        MatchingParenPolicyTestCase {
            description: "compiler policy ends a quote at a backslash-escaped quote",
            sql: r"('a\')' x) y",
            policy: QuotePolicy::COMPILER,
            expected_close: Ok(5),
        },
        MatchingParenPolicyTestCase {
            description: "sql lint policy honours backslash escapes",
            sql: r"('a\')' x) y",
            policy: QuotePolicy::SQL_LINT,
            expected_close: Ok(9),
        },
        MatchingParenPolicyTestCase {
            description: "single-quote backslash escapes do not apply to double quotes",
            sql: r#"("a\")" x) y"#,
            policy: BACKSLASH_ONLY,
            expected_close: Ok(5),
        },
        MatchingParenPolicyTestCase {
            description: "doubled quotes are escapes under every policy",
            sql: "('it''s )' x) y",
            policy: QUOTES_ONLY,
            expected_close: Ok(12),
        },
        MatchingParenPolicyTestCase {
            description: "block comments do not nest",
            sql: "(/* /* ) */ ) */ x) y",
            policy: QuotePolicy::COMPILER,
            expected_close: Ok(12),
        },
        MatchingParenPolicyTestCase {
            description: "compiler policy skips dollar-quoted text",
            sql: "($$ ) $$ x) y",
            policy: QuotePolicy::COMPILER,
            expected_close: Ok(10),
        },
        MatchingParenPolicyTestCase {
            description: "dollar quotes are code when the policy disables them",
            sql: "($$ ) $$ x) y",
            policy: QUOTES_ONLY,
            expected_close: Ok(4),
        },
        MatchingParenPolicyTestCase {
            description: "SQL lint policy skips dollar-quoted text like the compiler",
            sql: "($$ ) $$ x) y",
            policy: QuotePolicy::SQL_LINT,
            expected_close: Ok(10),
        },
        MatchingParenPolicyTestCase {
            description: "multibyte text keeps byte offsets on character boundaries",
            sql: "('é)ü' ñ x) y",
            policy: QuotePolicy::COMPILER,
            expected_close: Ok(13),
        },
        MatchingParenPolicyTestCase {
            description: "unterminated quote reports the quote",
            sql: "('abc x) y",
            policy: QuotePolicy::COMPILER,
            expected_close: Err(Unclosed::Quote),
        },
        MatchingParenPolicyTestCase {
            description: "unterminated block comment reports the comment",
            sql: "(/* abc x) y",
            policy: QUOTES_ONLY,
            expected_close: Err(Unclosed::BlockComment),
        },
        MatchingParenPolicyTestCase {
            description: "unclosed parenthesis reports the parenthesis",
            sql: "(a (b)",
            policy: QuotePolicy::SQL_LINT,
            expected_close: Err(Unclosed::Parenthesis),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            matching_paren(test_case.sql.as_bytes(), 0, test_case.policy),
            test_case.expected_close,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_comment_or_quote_starts_when_finding_non_code_end_then_returns_end_offset() {
    let test_cases = [
        NonCodeEndTestCase {
            description: "line comment ends after its newline",
            sql: "-- note\nSELECT",
            policy: QuotePolicy::COMPILER,
            expected_end: Ok(Some(8)),
        },
        NonCodeEndTestCase {
            description: "line comment without newline runs to the end",
            sql: "-- note",
            policy: QuotePolicy::COMPILER,
            expected_end: Ok(Some(7)),
        },
        NonCodeEndTestCase {
            description: "block comment ends after its terminator",
            sql: "/* a */ b",
            policy: QUOTES_ONLY,
            expected_end: Ok(Some(7)),
        },
        NonCodeEndTestCase {
            description: "backtick is code when the policy disables it",
            sql: "`a` b",
            policy: QuotePolicy::SQL_LINT,
            expected_end: Ok(None),
        },
        NonCodeEndTestCase {
            description: "trailing backslash leaves the quote unterminated",
            sql: r"'a\",
            policy: QuotePolicy::SQL_LINT,
            expected_end: Err(Unclosed::Quote),
        },
        NonCodeEndTestCase {
            description: "dollar quote hides apostrophes, comments and single dollars",
            sql: "$$it's -- $5 $$ b",
            policy: QuotePolicy::COMPILER,
            expected_end: Ok(Some(15)),
        },
        NonCodeEndTestCase {
            description: "tagged dollar quote ends only at its own tag",
            sql: "$tag$ $$ ) $tag$ b",
            policy: QuotePolicy::COMPILER,
            expected_end: Ok(Some(16)),
        },
        NonCodeEndTestCase {
            description: "unterminated dollar quote reports the quote",
            sql: "$$it's",
            policy: QuotePolicy::COMPILER,
            expected_end: Err(Unclosed::Quote),
        },
        NonCodeEndTestCase {
            description: "positional parameter is code",
            sql: "$1 $",
            policy: QuotePolicy::COMPILER,
            expected_end: Ok(None),
        },
        NonCodeEndTestCase {
            description: "digit-led tag is not a dollar quote",
            sql: "$1$ x $1$",
            policy: QuotePolicy::COMPILER,
            expected_end: Ok(None),
        },
        NonCodeEndTestCase {
            description: "plain code has no non-code end",
            sql: "SELECT 1",
            policy: QuotePolicy::COMPILER,
            expected_end: Ok(None),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            non_code_end(test_case.sql.as_bytes(), 0, test_case.policy),
            test_case.expected_end,
            "{}",
            test_case.description
        );
    }
}
