use sqlbuild_core::text::main::text_wrap::text_wrap;

use crate::argv::_helpers::text_wrap::normalize_whitespace;
use crate::argv::tests::test_types::WrapTestCase;

#[test]
fn given_help_text_when_wrapping_then_lines_match_python_textwrap() {
    let test_cases = [
        WrapTestCase {
            description: "hyphenated words break after the hyphen; options stay whole",
            text: "  write a read-only   report with --dry-run\n flags ",
            width: 14,
            indent: "",
            expected_lines: &["write a read-", "only report", "with --dry-run", "flags"],
        },
        WrapTestCase {
            description: "words longer than the line are split",
            text: "abcdefghij",
            width: 4,
            indent: "  ",
            expected_lines: &["  ab", "  cd", "  ef", "  gh", "  ij"],
        },
        WrapTestCase {
            description: "an em-dash between words is its own chunk",
            text: "orders--customers",
            width: 9,
            indent: "",
            expected_lines: &["orders--", "customers"],
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            text_wrap(
                &normalize_whitespace(test_case.text),
                test_case.width,
                (test_case.indent, test_case.indent),
                true
            ),
            test_case.expected_lines,
            "{}",
            test_case.description
        );
    }
}
