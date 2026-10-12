use crate::text::main::close_matches::close_matches;
use crate::text::main::glob_match::glob_match;
use crate::text::main::python_cleandoc::python_cleandoc;
use crate::text::tests::test_types::{CleandocTestCase, CloseMatchesTestCase, GlobTestCase};

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
fn given_words_when_finding_close_matches_then_the_most_similar_rank_first() {
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
            description: "a low cutoff still drops unrelated keys",
            word: "materialised",
            possibilities: KEYS,
            count: 3,
            cutoff: 0.3,
            expected_matches: &["materialized"],
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
            description: "an adjacent swap counts as one edit",
            word: "tgas",
            possibilities: KEYS,
            count: 1,
            cutoff: 0.6,
            expected_matches: &["tags"],
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
            description: "an exact match ranks before one substitution and a swap",
            word: "ab",
            possibilities: &["ba", "ab", "aB"],
            count: 3,
            cutoff: 0.0,
            expected_matches: &["ab", "aB", "ba"],
        },
        CloseMatchesTestCase {
            description: "equal scores rank alphabetically",
            word: "abc",
            possibilities: &["xyz", "cab", "bca"],
            count: 3,
            cutoff: 0.0,
            expected_matches: &["bca", "cab", "xyz"],
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
fn given_docstring_bodies_when_cleaning_then_common_indent_and_outer_blank_lines_go() {
    let test_cases = [
        CleandocTestCase {
            description: "leading whitespace on the first line and the common indent are stripped",
            text: "\u{c}first\n\u{3000}  second\n\u{3000} third",
            expected_text: "first\n second\nthird",
        },
        CleandocTestCase {
            description: "tabs expand before dedenting and trailing blank lines go",
            text: "  first\n    second\n\t third\n",
            expected_text: "first\nsecond\n     third",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            python_cleandoc(test_case.text),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_glob_patterns_when_matching_then_shell_wildcards_match() {
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
            glob_match(test_case.name, test_case.pattern),
            test_case.expected_match,
            "{}",
            test_case.description
        );
    }
}
