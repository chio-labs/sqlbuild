use crate::text::main::close_matches::close_matches;
use crate::text::main::is_python_alnum::is_python_alnum;
use crate::text::main::is_python_space::is_python_space;
use crate::text::main::is_python_word::is_python_word;
use crate::text::tests::test_types::{CharacterClassTestCase, CloseMatchesTestCase};

const KEYS: &[&str] = &[
    "audits",
    "columns",
    "constants",
    "description",
    "enums",
    "materialized",
    "tags",
    "unique_key",
];

#[test]
fn given_words_when_finding_close_matches_then_results_match_difflib() {
    let test_cases = [
        CloseMatchesTestCase {
            description: "one near key",
            word: "tagz",
            possibilities: KEYS,
            count: 1,
            cutoff: 0.6,
            expected_matches: &["tags"],
        },
        CloseMatchesTestCase {
            description: "ranked with a low cutoff",
            word: "materialised",
            possibilities: KEYS,
            count: 3,
            cutoff: 0.3,
            expected_matches: &["materialized", "tags", "description"],
        },
        CloseMatchesTestCase {
            description: "ranked after a deletion",
            word: "colums",
            possibilities: KEYS,
            count: 3,
            cutoff: 0.3,
            expected_matches: &["columns", "enums", "constants"],
        },
        CloseMatchesTestCase {
            description: "no candidate reaches the cutoff",
            word: "zzz",
            possibilities: KEYS,
            count: 1,
            cutoff: 0.6,
            expected_matches: &[],
        },
        CloseMatchesTestCase {
            description: "equal scores prefer the larger candidate",
            word: "ab",
            possibilities: &["ba", "ab", "aB"],
            count: 3,
            cutoff: 0.0,
            expected_matches: &["ab", "ba", "aB"],
        },
        CloseMatchesTestCase {
            description: "rotations score by their longest blocks",
            word: "abc",
            possibilities: &["xyz", "cab", "bca"],
            count: 3,
            cutoff: 0.0,
            expected_matches: &["cab", "bca", "xyz"],
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            close_matches(
                test_case.word,
                test_case.possibilities,
                test_case.count,
                test_case.cutoff
            ),
            test_case.expected_matches,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_characters_when_classifying_then_python_str_methods_agree() {
    let test_cases = [
        CharacterClassTestCase {
            description: "ASCII letter",
            character: 'a',
            expected_alnum: true,
            expected_word: true,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "underscore is a word character only",
            character: '_',
            expected_alnum: false,
            expected_word: true,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "Arabic-Indic digit",
            character: '\u{663}',
            expected_alnum: true,
            expected_word: true,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "letter number",
            character: '\u{2167}',
            expected_alnum: true,
            expected_word: true,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "combining mark that Rust calls alphabetic",
            character: '\u{345}',
            expected_alnum: false,
            expected_word: false,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "circled letter symbol",
            character: '\u{24b6}',
            expected_alnum: false,
            expected_word: false,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "information separator is whitespace",
            character: '\u{1c}',
            expected_alnum: false,
            expected_word: false,
            expected_space: true,
        },
        CharacterClassTestCase {
            description: "ideographic space",
            character: '\u{3000}',
            expected_alnum: false,
            expected_word: false,
            expected_space: true,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            (
                is_python_alnum(test_case.character),
                is_python_word(test_case.character),
                is_python_space(test_case.character)
            ),
            (
                test_case.expected_alnum,
                test_case.expected_word,
                test_case.expected_space
            ),
            "{}",
            test_case.description
        );
    }
}
