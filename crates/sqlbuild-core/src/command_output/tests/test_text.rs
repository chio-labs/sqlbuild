use crate::command_output::_helpers::text::{split_lines, strip_ansi};
use crate::command_output::tests::test_types::TextTestCase;

#[test]
fn given_terminal_control_sequences_when_stripping_then_only_complete_sequences_are_removed() {
    let test_cases = [
        TextTestCase {
            description: "colour codes around text",
            text: "\u{1b}[1;32mok\u{1b}[0m done",
            expected_parts: &["ok done"],
        },
        TextTestCase {
            description: "hyperlink terminated by BEL and by ST",
            text: "\u{1b}]8;;https://example.com\u{7}link\u{1b}]8;;\u{1b}\\",
            expected_parts: &["link"],
        },
        TextTestCase {
            description: "unterminated sequences stay",
            text: "\u{1b}]title\u{1b}[12",
            expected_parts: &["\u{1b}]title\u{1b}[12"],
        },
    ];

    for test_case in test_cases {
        let plain = String::from_utf8(strip_ansi(test_case.text.as_bytes())).unwrap_or_default();

        assert_eq!(
            [plain.as_str()].as_slice(),
            test_case.expected_parts,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_mixed_line_boundaries_when_splitting_then_matches_python_splitlines_keepends() {
    let test_cases = [
        TextTestCase {
            description: "newline, carriage return pair and trailing text",
            text: "a\nb\r\nc\rd",
            expected_parts: &["a\n", "b\r\n", "c\r", "d"],
        },
        TextTestCase {
            description: "form feed, file separators and unicode separators",
            text: "a\u{c}b\u{1c}c\u{85}d\u{2028}e\u{2029}",
            expected_parts: &["a\u{c}", "b\u{1c}", "c\u{85}", "d\u{2028}", "e\u{2029}"],
        },
        TextTestCase {
            description: "empty text has no lines",
            text: "",
            expected_parts: &[],
        },
    ];

    for test_case in test_cases {
        let lines: Vec<String> = split_lines(test_case.text.as_bytes())
            .into_iter()
            .map(|line| String::from_utf8_lossy(line).into_owned())
            .collect();

        assert_eq!(lines, test_case.expected_parts, "{}", test_case.description);
    }
}
