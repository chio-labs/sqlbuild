use crate::sql_scan::main::matching_paren::matching_paren;
use crate::sql_scan::main::non_code_end::non_code_end;
use crate::sql_scan::models::QuotePolicy;
use crate::sql_scan::models::Unclosed;
use crate::sql_scan::tests::test_types::{MatchingParenPolicyTestCase, NonCodeEndTestCase};

const BACKSLASH_ONLY: QuotePolicy = QuotePolicy {
    backtick_identifiers: false,
    single_quote_backslash_escapes: true,
    double_quote_backslash_escapes: false,
};

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
            description: "rules policy treats backticks as code",
            sql: "(`a)b` x) y",
            policy: QuotePolicy::RULES,
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
            policy: QuotePolicy::RULES,
            expected_close: Ok(12),
        },
        MatchingParenPolicyTestCase {
            description: "block comments do not nest",
            sql: "(/* /* ) */ ) */ x) y",
            policy: QuotePolicy::COMPILER,
            expected_close: Ok(12),
        },
        MatchingParenPolicyTestCase {
            description: "dollar quotes are scanned as code",
            sql: "($$ ) $$ x) y",
            policy: QuotePolicy::COMPILER,
            expected_close: Ok(4),
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
            policy: QuotePolicy::RULES,
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
            policy: QuotePolicy::RULES,
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
