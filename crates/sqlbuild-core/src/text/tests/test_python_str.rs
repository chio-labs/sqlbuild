use crate::text::main::python_casefold::python_casefold;
use crate::text::main::python_isalnum::python_isalnum;
use crate::text::main::python_isdigit::python_isdigit;
use crate::text::main::python_isspace::python_isspace;
use crate::text::main::python_splitlines::python_splitlines;
use crate::text::tests::test_types::{
    CasefoldTestCase, CharacterClassTestCase, SplitlinesTestCase,
};

/// Expectations recorded from CPython 3.12.
#[test]
fn given_text_when_casefolding_then_matches_python_casefold() {
    let test_cases = [
        CasefoldTestCase {
            description: "final sigma folds to sigma",
            text: "ΟΔΟΣ",
            expected_folded: "οδοσ",
        },
        CasefoldTestCase {
            description: "lowercase final sigma",
            text: "οδος",
            expected_folded: "οδοσ",
        },
        CasefoldTestCase {
            description: "sharp s expands",
            text: "Straße",
            expected_folded: "strasse",
        },
        CasefoldTestCase {
            description: "ligature expands",
            text: "\u{fb01}le",
            expected_folded: "file",
        },
        CasefoldTestCase {
            description: "long s",
            text: "\u{17f}",
            expected_folded: "s",
        },
        CasefoldTestCase {
            description: "micro sign",
            text: "\u{b5}",
            expected_folded: "\u{3bc}",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            python_casefold(test_case.text),
            test_case.expected_folded,
            "{}",
            test_case.description
        );
    }
}

/// Expectations recorded from CPython 3.12.
#[test]
fn given_characters_when_classifying_then_matches_python_str_predicates() {
    let test_cases = [
        CharacterClassTestCase {
            description: "ascii letter",
            character: 'a',
            expected_alnum: true,
            expected_digit: false,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "combining vowel sign",
            character: '\u{93e}',
            expected_alnum: false,
            expected_digit: false,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "arabic-indic digit",
            character: '٣',
            expected_alnum: true,
            expected_digit: true,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "circled digit",
            character: '①',
            expected_alnum: true,
            expected_digit: true,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "subscript digit",
            character: '₃',
            expected_alnum: true,
            expected_digit: true,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "vulgar fraction",
            character: '½',
            expected_alnum: true,
            expected_digit: false,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "unit separator",
            character: '\u{1f}',
            expected_alnum: false,
            expected_digit: false,
            expected_space: true,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            python_isalnum(test_case.character),
            test_case.expected_alnum,
            "{}",
            test_case.description
        );
        assert_eq!(
            python_isdigit(test_case.character),
            test_case.expected_digit,
            "{}",
            test_case.description
        );
        assert_eq!(
            python_isspace(test_case.character),
            test_case.expected_space,
            "{}",
            test_case.description
        );
    }
}

/// Expectations recorded from CPython 3.12.
#[test]
fn given_text_when_splitting_lines_then_matches_python_splitlines() {
    let test_cases = [
        SplitlinesTestCase {
            description: "every Python line boundary, with CRLF as one",
            text: "a\r\nb\rc\u{1c}d\u{2028}\n",
            expected_lines: &["a", "b", "c", "d", ""],
        },
        SplitlinesTestCase {
            description: "empty text has no lines",
            text: "",
            expected_lines: &[],
        },
        SplitlinesTestCase {
            description: "a final newline ends the last line",
            text: "one\n",
            expected_lines: &["one"],
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            python_splitlines(test_case.text),
            test_case.expected_lines,
            "{}",
            test_case.description
        );
    }
}
