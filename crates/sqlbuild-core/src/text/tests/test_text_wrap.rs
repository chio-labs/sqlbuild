use crate::text::main::cell_len::cell_len;
use crate::text::main::text_wrap::text_wrap;
use crate::text::tests::test_types::{CellLenTestCase, TextWrapTestCase};

#[test]
fn given_prose_when_wrapping_then_lines_match_python_textwrap() {
    let test_cases = [
        TextWrapTestCase {
            description: "the first line takes the initial indent, later lines the subsequent one",
            text: "add a description to the MODEL header",
            width: 30,
            indents: ("  = help: ", "          "),
            expected_lines: &[
                "  = help: add a description to",
                "          the MODEL header",
            ],
        },
        TextWrapTestCase {
            description: "newlines and tabs become spaces",
            text: "a\tb\nc",
            width: 40,
            indents: ("", ""),
            expected_lines: &["a       b c"],
        },
        TextWrapTestCase {
            description: "empty text has no lines",
            text: "",
            width: 10,
            indents: ("> ", "> "),
            expected_lines: &[],
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            text_wrap(test_case.text, test_case.width, test_case.indents, true),
            test_case.expected_lines,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_text_when_measuring_cells_then_wide_characters_count_twice() {
    let test_cases = [
        CellLenTestCase {
            description: "ascii is one cell per character",
            text: "orders",
            expected_cells: 6,
        },
        CellLenTestCase {
            description: "CJK characters are wide",
            text: "注文",
            expected_cells: 4,
        },
        CellLenTestCase {
            description: "combining marks take no cells",
            text: "e\u{301}",
            expected_cells: 1,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            cell_len(test_case.text),
            test_case.expected_cells,
            "{}",
            test_case.description
        );
    }
}
