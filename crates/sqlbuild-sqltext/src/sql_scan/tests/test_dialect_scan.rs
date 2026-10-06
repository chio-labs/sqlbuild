use crate::sql_scan::main::dialect_non_code_ranges::dialect_non_code_ranges;
use crate::sql_scan::tests::helpers::{
    escape_strings, generic, raw_strings, single_quote_backslashes, triple_quotes,
};
use crate::sql_scan::tests::test_types::{
    DialectFirstNonCodeRangeTestCase, DialectNonCodeRangesTestCase,
};

#[test]
fn given_dialect_lexical_syntax_when_scanning_non_code_then_dialect_decides_boundaries() {
    let test_cases = [
        DialectFirstNonCodeRangeTestCase {
            description: "generic sql ends a quote at a backslash-escaped quote",
            sql: r"'O\'Brien' x",
            syntax: generic(),
            expected_first_range: Some((0, 4)),
        },
        DialectFirstNonCodeRangeTestCase {
            description: "backslash escapes keep the quote open",
            sql: r"'O\'Brien' x",
            syntax: single_quote_backslashes(),
            expected_first_range: Some((0, 10)),
        },
        DialectFirstNonCodeRangeTestCase {
            description: "escape strings honour backslashes",
            sql: r"E'O\'Brien' x",
            syntax: escape_strings(),
            expected_first_range: Some((1, 11)),
        },
        DialectFirstNonCodeRangeTestCase {
            description: "plain strings keep backslashes literal under escape-string rules",
            sql: r"'C:\' x",
            syntax: escape_strings(),
            expected_first_range: Some((0, 5)),
        },
        DialectFirstNonCodeRangeTestCase {
            description: "raw strings disable backslash escapes",
            sql: r"r'C:\' x",
            syntax: raw_strings(),
            expected_first_range: Some((1, 6)),
        },
        DialectFirstNonCodeRangeTestCase {
            description: "triple quotes contain single quotes",
            sql: "'''it's''' x",
            syntax: triple_quotes(),
            expected_first_range: Some((0, 10)),
        },
        DialectFirstNonCodeRangeTestCase {
            description: "hash starts a line comment",
            sql: "# note\nx",
            syntax: triple_quotes(),
            expected_first_range: Some((0, 7)),
        },
        DialectFirstNonCodeRangeTestCase {
            description: "slash pair starts a line comment",
            sql: "// note\nx",
            syntax: single_quote_backslashes(),
            expected_first_range: Some((0, 8)),
        },
        DialectFirstNonCodeRangeTestCase {
            description: "nested block comments end at the outer close",
            sql: "/* a /* b */ c */ x",
            syntax: escape_strings(),
            expected_first_range: Some((0, 17)),
        },
        DialectFirstNonCodeRangeTestCase {
            description: "flat block comments end at the first close",
            sql: "/* a /* b */ c */ x",
            syntax: generic(),
            expected_first_range: Some((0, 12)),
        },
        DialectFirstNonCodeRangeTestCase {
            description: "an unclosed backslash-escaped quote extends to the end",
            sql: r"'O\'",
            syntax: single_quote_backslashes(),
            expected_first_range: Some((0, 4)),
        },
    ];
    for test_case in test_cases {
        let ranges: Vec<(usize, usize)> = dialect_non_code_ranges(test_case.sql, &test_case.syntax);
        assert_eq!(
            ranges.first().copied(),
            test_case.expected_first_range,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_quoted_text_before_a_marker_when_collecting_non_code_ranges_then_dialect_decides_coverage()
{
    let test_cases = [
        DialectNonCodeRangesTestCase {
            description: "backslash escapes keep a later marker in code",
            sql: r#"SELECT 'O\'Brien' AS name FROM __ref("orders")"#,
            syntax: single_quote_backslashes(),
            expected_marker_protected: false,
        },
        DialectNonCodeRangesTestCase {
            description: "generic sql reads a later marker as quoted text",
            sql: r#"SELECT 'O\'Brien' AS name FROM __ref("orders")"#,
            syntax: generic(),
            expected_marker_protected: true,
        },
    ];
    for test_case in test_cases {
        let ranges: Vec<(usize, usize)> = dialect_non_code_ranges(test_case.sql, &test_case.syntax);
        let marker: usize = test_case.sql.find("__ref").unwrap_or_default();
        let protected: bool = ranges
            .iter()
            .any(|(start, end)| marker >= *start && marker < *end);
        assert_eq!(
            protected, test_case.expected_marker_protected,
            "{}",
            test_case.description
        );
    }
}
