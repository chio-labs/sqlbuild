use crate::sql_scan::main::lexical_syntax_key::lexical_syntax_key;
use crate::sql_scan::main::reads_differently_from_generic::reads_differently_from_generic;
use crate::sql_scan::main::unsupported_line_comment_prefixes::unsupported_line_comment_prefixes;
use crate::sql_scan::tests::helpers::syntax;
use crate::sql_scan::tests::test_types::{LexicalRulesTestCase, PrefixCheckTestCase};

#[test]
fn given_lexical_rules_when_keyed_and_compared_then_match_python_properties() {
    let test_cases = [
        LexicalRulesTestCase {
            description: "generic rules read SQL as generic SQL",
            syntax: syntax(&[], [false; 4], &["--"]),
            sql: "select '\\' -- note",
            expected_key: "|False|False|False|False|--",
            expected_reads_differently: false,
        },
        LexicalRulesTestCase {
            description: "backslash quotes change escaped text",
            syntax: syntax(&["\"", "'"], [false, true, false, false], &["--", "#"]),
            sql: "select 'a\\'",
            expected_key: "\",'|False|True|False|False|#,--",
            expected_reads_differently: true,
        },
        LexicalRulesTestCase {
            description: "nested comments need two openers",
            syntax: syntax(&[], [false, false, false, true], &["--"]),
            sql: "/* a /* b */ */ select 1",
            expected_key: "|False|False|False|True|--",
            expected_reads_differently: true,
        },
        LexicalRulesTestCase {
            description: "a hash comment prefix reads hash text",
            syntax: syntax(&[], [false; 4], &["--", "#"]),
            sql: "select 1 # trailing",
            expected_key: "|False|False|False|False|#,--",
            expected_reads_differently: true,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            (
                lexical_syntax_key(&test_case.syntax),
                reads_differently_from_generic(&test_case.syntax, test_case.sql),
            ),
            (
                test_case.expected_key.to_owned(),
                test_case.expected_reads_differently
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_declared_prefixes_when_checking_then_only_unsupported_ones_are_returned() {
    let test_cases = [
        PrefixCheckTestCase {
            description: "unsupported prefixes are sorted without repeats",
            declared: &["%", "--", "%", ";"],
            expected_unsupported: &["%", ";"],
        },
        PrefixCheckTestCase {
            description: "supported prefixes pass",
            declared: &["#", "//", "--"],
            expected_unsupported: &[],
        },
    ];
    for test_case in test_cases {
        let declared: Vec<String> = test_case
            .declared
            .iter()
            .map(|prefix| (*prefix).to_owned())
            .collect();
        assert_eq!(
            unsupported_line_comment_prefixes(&declared),
            test_case.expected_unsupported,
            "{}",
            test_case.description
        );
    }
}
