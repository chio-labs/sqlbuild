use crate::text::main::close_matches::close_matches;
use crate::text::main::is_python_alnum::is_python_alnum;
use crate::text::main::is_python_alpha::is_python_alpha;
use crate::text::main::is_python_space::is_python_space;
use crate::text::main::is_python_word::is_python_word;
use crate::text::main::python_cleandoc::python_cleandoc;
use crate::text::main::python_text::python_text;
use crate::text::models::PythonText;
use crate::text::tests::test_types::{
    CharacterClassTestCase, CleandocTestCase, CloseMatchesTestCase, PythonTextTestCase,
};

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
            expected_alpha: true,
            expected_alnum: true,
            expected_word: true,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "underscore is a word character only",
            character: '_',
            expected_alpha: false,
            expected_alnum: false,
            expected_word: true,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "Arabic-Indic digit",
            character: '\u{663}',
            expected_alpha: false,
            expected_alnum: true,
            expected_word: true,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "letter number",
            character: '\u{2167}',
            expected_alpha: false,
            expected_alnum: true,
            expected_word: true,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "combining mark that Rust calls alphabetic",
            character: '\u{345}',
            expected_alpha: false,
            expected_alnum: false,
            expected_word: false,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "circled letter symbol",
            character: '\u{24b6}',
            expected_alpha: false,
            expected_alnum: false,
            expected_word: false,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "information separator is whitespace",
            character: '\u{1c}',
            expected_alpha: false,
            expected_alnum: false,
            expected_word: false,
            expected_space: true,
        },
        CharacterClassTestCase {
            description: "Latin letter with an accent is alphabetic",
            character: '\u{e9}',
            expected_alpha: true,
            expected_alnum: true,
            expected_word: true,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "ideographic space",
            character: '\u{3000}',
            expected_alpha: false,
            expected_alnum: false,
            expected_word: false,
            expected_space: true,
        },
    ];
    let python: PythonText = python_text((3, 12), "15.0.0").expect("Python 3.12 is supported");
    for test_case in test_cases {
        assert_eq!(
            (
                is_python_alpha(python, test_case.character),
                is_python_alnum(python, test_case.character),
                is_python_word(python, test_case.character),
                is_python_space(test_case.character)
            ),
            (
                test_case.expected_alpha,
                test_case.expected_alnum,
                test_case.expected_word,
                test_case.expected_space
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_python_runtimes_when_selecting_text_semantics_then_tables_follow_unicode_version() {
    let test_cases = [
        PythonTextTestCase {
            description: "Python 3.12 with Unicode 15.0 predates CJK extension I",
            python_version: (3, 12),
            unicode_version: "15.0.0",
            expected_alnum: Some([false, false]),
        },
        PythonTextTestCase {
            description: "Python 3.13 with Unicode 15.1 adds CJK extension I",
            python_version: (3, 13),
            unicode_version: "15.1.0",
            expected_alnum: Some([true, false]),
        },
        PythonTextTestCase {
            description: "Python 3.14 with Unicode 16.0 adds the Garay script",
            python_version: (3, 14),
            unicode_version: "16.0.0",
            expected_alnum: Some([true, true]),
        },
        PythonTextTestCase {
            description: "an unknown Unicode version defers",
            python_version: (3, 14),
            unicode_version: "17.0.0",
            expected_alnum: None,
        },
        PythonTextTestCase {
            description: "an unknown Python version defers",
            python_version: (3, 15),
            unicode_version: "16.0.0",
            expected_alnum: None,
        },
        PythonTextTestCase {
            description: "an older Python defers",
            python_version: (3, 11),
            unicode_version: "15.0.0",
            expected_alnum: None,
        },
    ];
    for test_case in test_cases {
        let alnum: Option<[bool; 2]> =
            python_text(test_case.python_version, test_case.unicode_version).map(|python| {
                [
                    is_python_alnum(python, '\u{2ebf0}'),
                    is_python_alnum(python, '\u{10d40}'),
                ]
            });
        assert_eq!(alnum, test_case.expected_alnum, "{}", test_case.description);
    }
}

#[test]
fn given_python_versions_when_cleaning_bodies_then_cleandoc_matches_that_version() {
    let test_cases = [
        CleandocTestCase {
            description: "3.12 strips any leading whitespace",
            python_version: (3, 12),
            unicode_version: "15.0.0",
            text: "\u{c}first\n\u{3000}  second\n\u{3000} third",
            expected_text: "first\n second\nthird",
        },
        CleandocTestCase {
            description: "3.13 strips leading spaces only",
            python_version: (3, 13),
            unicode_version: "15.1.0",
            text: "\u{c}first\n\u{3000}  second\n  third",
            expected_text: "\u{c}first\n\u{3000}  second\n  third",
        },
        CleandocTestCase {
            description: "3.14 dedents by the common run of spaces",
            python_version: (3, 14),
            unicode_version: "16.0.0",
            text: "  first\n    second\n\t third\n",
            expected_text: "first\nsecond\n     third",
        },
    ];
    for test_case in test_cases {
        let python: PythonText = python_text(test_case.python_version, test_case.unicode_version)
            .expect("supported runtime");
        assert_eq!(
            python_cleandoc(python, test_case.text),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}
