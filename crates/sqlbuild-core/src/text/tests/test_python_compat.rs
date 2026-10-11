use crate::text::main::close_matches::close_matches;
use crate::text::main::is_python_alnum::is_python_alnum;
use crate::text::main::is_python_alpha::is_python_alpha;
use crate::text::main::is_python_decimal::is_python_decimal;
use crate::text::main::is_python_space::is_python_space;
use crate::text::main::is_python_word::is_python_word;
use crate::text::main::python_casefold::python_casefold;
use crate::text::main::python_cleandoc::python_cleandoc;
use crate::text::main::python_fnmatchcase::python_fnmatchcase;
use crate::text::main::python_ignorecase_key::python_ignorecase_key;
use crate::text::main::python_splitlines::python_splitlines;
use crate::text::main::python_str_repr::python_str_repr;
use crate::text::main::python_text::python_text;
use crate::text::main::python_upper::python_upper;
use crate::text::models::PythonText;
use crate::text::tests::test_types::{
    CaseMappingTestCase, CharacterClassTestCase, CleandocTestCase, CloseMatchesTestCase,
    GlobTestCase, IgnorecaseTestCase, PythonTextTestCase, ReprTestCase, SplitlinesTestCase,
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
            expected_decimal: false,
            expected_alpha: true,
            expected_alnum: true,
            expected_word: true,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "underscore is a word character only",
            character: '_',
            expected_decimal: false,
            expected_alpha: false,
            expected_alnum: false,
            expected_word: true,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "Arabic-Indic digit",
            character: '\u{663}',
            expected_decimal: true,
            expected_alpha: false,
            expected_alnum: true,
            expected_word: true,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "letter number",
            character: '\u{2167}',
            expected_decimal: false,
            expected_alpha: false,
            expected_alnum: true,
            expected_word: true,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "combining mark that Rust calls alphabetic",
            character: '\u{345}',
            expected_decimal: false,
            expected_alpha: false,
            expected_alnum: false,
            expected_word: false,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "circled letter symbol",
            character: '\u{24b6}',
            expected_decimal: false,
            expected_alpha: false,
            expected_alnum: false,
            expected_word: false,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "information separator is whitespace",
            character: '\u{1c}',
            expected_decimal: false,
            expected_alpha: false,
            expected_alnum: false,
            expected_word: false,
            expected_space: true,
        },
        CharacterClassTestCase {
            description: "Latin letter with an accent is alphabetic",
            character: '\u{e9}',
            expected_decimal: false,
            expected_alpha: true,
            expected_alnum: true,
            expected_word: true,
            expected_space: false,
        },
        CharacterClassTestCase {
            description: "ideographic space",
            character: '\u{3000}',
            expected_decimal: false,
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
                is_python_decimal(python, test_case.character),
                is_python_alpha(python, test_case.character),
                is_python_alnum(python, test_case.character),
                is_python_word(python, test_case.character),
                is_python_space(test_case.character)
            ),
            (
                test_case.expected_decimal,
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

#[test]
fn given_unicode_versions_when_folding_and_upper_casing_then_python_str_methods_agree() {
    let test_cases = [
        CaseMappingTestCase {
            description: "ASCII, final sigma, sharp s, dotted I and a ligature",
            unicode_version: "15.0.0",
            text: "Orders \u{3a3}\u{391}\u{3a3} \u{df} \u{130} \u{fb01}",
            expected_casefold: "orders \u{3c3}\u{3b1}\u{3c3} ss i\u{307} fi",
            expected_upper: "ORDERS \u{3a3}\u{391}\u{3a3} SS \u{130} FI",
        },
        CaseMappingTestCase {
            description: "a capital Unicode 16.0 added folds only there",
            unicode_version: "15.1.0",
            text: "\u{a7cb}",
            expected_casefold: "\u{a7cb}",
            expected_upper: "\u{a7cb}",
        },
        CaseMappingTestCase {
            description: "the same capital under Unicode 16.0",
            unicode_version: "16.0.0",
            text: "\u{a7cb}",
            expected_casefold: "\u{264}",
            expected_upper: "\u{a7cb}",
        },
    ];
    for test_case in test_cases {
        let python: PythonText =
            python_text((3, 13), test_case.unicode_version).expect("the version is supported");

        assert_eq!(
            (
                python_casefold(python, test_case.text),
                python_upper(python, test_case.text)
            ),
            (
                test_case.expected_casefold.to_owned(),
                test_case.expected_upper.to_owned()
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_character_pairs_when_matching_ignoring_case_then_python_re_agrees() {
    let test_cases = [
        IgnorecaseTestCase {
            description: "k against \u{212a}",
            pattern: 'k',
            text: '\u{212a}',
            expected_match: true,
        },
        IgnorecaseTestCase {
            description: "K against \u{212a}",
            pattern: 'K',
            text: '\u{212a}',
            expected_match: true,
        },
        IgnorecaseTestCase {
            description: "s against \u{17f}",
            pattern: 's',
            text: '\u{17f}',
            expected_match: true,
        },
        IgnorecaseTestCase {
            description: "i against \u{131}",
            pattern: 'i',
            text: '\u{131}',
            expected_match: true,
        },
        IgnorecaseTestCase {
            description: "I against \u{130}",
            pattern: 'I',
            text: '\u{130}',
            expected_match: true,
        },
        IgnorecaseTestCase {
            description: "i against \u{130}",
            pattern: 'i',
            text: '\u{130}',
            expected_match: true,
        },
        IgnorecaseTestCase {
            description: "\u{3c3} against \u{3c2}",
            pattern: '\u{3c3}',
            text: '\u{3c2}',
            expected_match: true,
        },
        IgnorecaseTestCase {
            description: "\u{3a3} against \u{3c2}",
            pattern: '\u{3a3}',
            text: '\u{3c2}',
            expected_match: true,
        },
        IgnorecaseTestCase {
            description: "\u{b5} against \u{39c}",
            pattern: '\u{b5}',
            text: '\u{39c}',
            expected_match: true,
        },
        IgnorecaseTestCase {
            description: "\u{df} against \u{1e9e}",
            pattern: '\u{df}',
            text: '\u{1e9e}',
            expected_match: true,
        },
        IgnorecaseTestCase {
            description: "\u{df} against S",
            pattern: '\u{df}',
            text: 'S',
            expected_match: false,
        },
        IgnorecaseTestCase {
            description: "\u{130} against \u{131}",
            pattern: '\u{130}',
            text: '\u{131}',
            expected_match: true,
        },
        IgnorecaseTestCase {
            description: "a against \u{e1}",
            pattern: 'a',
            text: '\u{e1}',
            expected_match: false,
        },
        IgnorecaseTestCase {
            description: "\u{1c80} against \u{412}",
            pattern: '\u{1c80}',
            text: '\u{412}',
            expected_match: true,
        },
        IgnorecaseTestCase {
            description: "\u{fb05} against \u{fb06}",
            pattern: '\u{fb05}',
            text: '\u{fb06}',
            expected_match: true,
        },
    ];
    let python: PythonText = python_text((3, 12), "15.0.0").expect("Python 3.12 is supported");
    for test_case in test_cases {
        assert_eq!(
            python_ignorecase_key(python, test_case.pattern)
                == python_ignorecase_key(python, test_case.text),
            test_case.expected_match,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_text_when_taking_repr_then_it_matches_python() {
    let test_cases = [
        ReprTestCase {
            description: "plain text uses single quotes",
            unicode_version: "16.0.0",
            value: "plain",
            expected_repr: "'plain'",
        },
        ReprTestCase {
            description: "a single quote alone switches to double quotes",
            unicode_version: "16.0.0",
            value: "it's",
            expected_repr: "\"it's\"",
        },
        ReprTestCase {
            description: "both quotes keep single quotes and escape them",
            unicode_version: "16.0.0",
            value: "both'\"",
            expected_repr: "'both\\'\"'",
        },
        ReprTestCase {
            description: "whitespace controls and backslashes use short escapes",
            unicode_version: "16.0.0",
            value: "tab\tnew\nline\r\\",
            expected_repr: "'tab\\tnew\\nline\\r\\\\'",
        },
        ReprTestCase {
            description: "other controls use hex escapes",
            unicode_version: "16.0.0",
            value: "bell\u{7}del\u{7f}",
            expected_repr: "'bell\\x07del\\x7f'",
        },
        ReprTestCase {
            description: "printable Latin-1 text stays literal",
            unicode_version: "16.0.0",
            value: "caf\u{e9}",
            expected_repr: "'caf\u{e9}'",
        },
        ReprTestCase {
            description: "non-printable Latin-1 uses hex escapes",
            unicode_version: "16.0.0",
            value: "\u{a0}\u{ad}",
            expected_repr: "'\\xa0\\xad'",
        },
        ReprTestCase {
            description: "format and separator characters use short Unicode escapes",
            unicode_version: "16.0.0",
            value: "\u{200b}\u{2028}\u{378}",
            expected_repr: "'\\u200b\\u2028\\u0378'",
        },
        ReprTestCase {
            description: "astral printable text stays literal and tags use long escapes",
            unicode_version: "16.0.0",
            value: "\u{1F600}\u{E0001}",
            expected_repr: "'\u{1F600}\\U000e0001'",
        },
        ReprTestCase {
            description: "a combining mark after a letter stays literal",
            unicode_version: "16.0.0",
            value: "e\u{301}",
            expected_repr: "'e\u{301}'",
        },
        ReprTestCase {
            description: "a quote with non-ASCII text still switches quotes",
            unicode_version: "16.0.0",
            value: "it\u{e9}'s",
            expected_repr: "\"it\u{e9}'s\"",
        },
        ReprTestCase {
            description: "a Unicode 16.0 emoji is escaped under Unicode 15.1",
            unicode_version: "15.1.0",
            value: "\u{1FAE9}",
            expected_repr: "'\\U0001fae9'",
        },
        ReprTestCase {
            description: "the same emoji is printable under Unicode 16.0",
            unicode_version: "16.0.0",
            value: "\u{1FAE9}",
            expected_repr: "'\u{1FAE9}'",
        },
        ReprTestCase {
            description: "a Unicode 16.0 capital is escaped under Unicode 15.0",
            unicode_version: "15.0.0",
            value: "\u{1C89}",
            expected_repr: "'\\u1c89'",
        },
    ];
    for test_case in test_cases {
        let python: PythonText =
            python_text((3, 13), test_case.unicode_version).expect("the version is supported");

        assert_eq!(
            python_str_repr(python, test_case.value),
            test_case.expected_repr,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_glob_patterns_when_matching_then_results_match_fnmatchcase() {
    let test_cases = [
        GlobTestCase {
            description: "ord* against orders",
            pattern: "ord*",
            name: "orders",
            expected_match: true,
        },
        GlobTestCase {
            description: "o?ders against orders",
            pattern: "o?ders",
            name: "orders",
            expected_match: true,
        },
        GlobTestCase {
            description: "[a-c]* against customers",
            pattern: "[a-c]*",
            name: "customers",
            expected_match: true,
        },
        GlobTestCase {
            description: "[!a-c]* against customers",
            pattern: "[!a-c]*",
            name: "customers",
            expected_match: false,
        },
        GlobTestCase {
            description: "[z-a]x against x",
            pattern: "[z-a]x",
            name: "x",
            expected_match: false,
        },
        GlobTestCase {
            description: "[]] against ]",
            pattern: "[]]",
            name: "]",
            expected_match: true,
        },
        GlobTestCase {
            description: "[!] against !",
            pattern: "[!]",
            name: "!",
            expected_match: false,
        },
        GlobTestCase {
            description: "[a-] against -",
            pattern: "[a-]",
            name: "-",
            expected_match: true,
        },
        GlobTestCase {
            description: "[ against [",
            pattern: "[",
            name: "[",
            expected_match: true,
        },
        GlobTestCase {
            description: "a[b against a[b",
            pattern: "a[b",
            name: "a[b",
            expected_match: true,
        },
        GlobTestCase {
            description: "**s against orders",
            pattern: "**s",
            name: "orders",
            expected_match: true,
        },
        GlobTestCase {
            description: "[^o]* against orders",
            pattern: "[^o]*",
            name: "orders",
            expected_match: true,
        },
        GlobTestCase {
            description: "[\\]x against \\x",
            pattern: "[\\]x",
            name: "\\x",
            expected_match: true,
        },
        GlobTestCase {
            description: "[!b-a] drops its empty range and matches any character",
            pattern: "[!b-a]",
            name: "\n",
            expected_match: true,
        },
        GlobTestCase {
            description: "[a-b-a] reads the second hyphen as a literal",
            pattern: "[a-b-a]",
            name: "-",
            expected_match: true,
        },
        GlobTestCase {
            description: "* matches across newlines",
            pattern: "a*b",
            name: "a\nb",
            expected_match: true,
        },
        GlobTestCase {
            description: "? matches one non-ASCII character",
            pattern: "caf?",
            name: "caf\u{e9}",
            expected_match: true,
        },
        GlobTestCase {
            description: "matching is case-sensitive",
            pattern: "Orders",
            name: "orders",
            expected_match: false,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            python_fnmatchcase(test_case.name, test_case.pattern),
            test_case.expected_match,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_text_when_splitting_lines_then_it_matches_str_splitlines() {
    let test_cases = [
        SplitlinesTestCase {
            description: "a newline separates two lines",
            text: "a\nb",
            expected_lines: &["a", "b"],
        },
        SplitlinesTestCase {
            description: "CRLF is one break and a trailing break adds no line",
            text: "a\r\nb\r",
            expected_lines: &["a", "b"],
        },
        SplitlinesTestCase {
            description: "Unicode separators, NEL and vertical tab break lines",
            text: "a\u{2028}b\u{85}c\u{b}d",
            expected_lines: &["a", "b", "c", "d"],
        },
        SplitlinesTestCase {
            description: "leading breaks give empty lines",
            text: "\n\nx",
            expected_lines: &["", "", "x"],
        },
        SplitlinesTestCase {
            description: "empty text has no lines",
            text: "",
            expected_lines: &[],
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
