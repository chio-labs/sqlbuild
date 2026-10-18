use sqlbuild_core::text::main::ignorecase_key::ignorecase_key;

use crate::assembly::analysis_session::main::names_set_operation::names_set_operation;
use crate::assembly::analysis_session::tests::test_types::{
    KeywordFoldingTestCase, NamesSetOperationTestCase,
};

#[test]
fn given_sql_when_checking_for_set_operations_then_matches_whole_words_in_any_case() {
    let test_cases = [
        NamesSetOperationTestCase {
            description: "a lowercase union is found",
            sql: "select 1 union all select 2",
            expected_set_operation: true,
        },
        NamesSetOperationTestCase {
            description: "a mixed-case intersect is found",
            sql: "SELECT a FROM t InTeRsEcT SELECT a FROM u",
            expected_set_operation: true,
        },
        NamesSetOperationTestCase {
            description: "a keyword at the end of the text is found",
            sql: "select a from t\nexcept",
            expected_set_operation: true,
        },
        NamesSetOperationTestCase {
            description: "a keyword inside an identifier is ignored",
            sql: "select reunion_id, union_count, except_flag from t",
            expected_set_operation: false,
        },
        NamesSetOperationTestCase {
            description: "a keyword followed by a non-ASCII letter is ignored",
            sql: "select 1 as unioné",
            expected_set_operation: false,
        },
        NamesSetOperationTestCase {
            description: "a keyword after a non-ASCII letter is ignored",
            sql: "select 1 as éunion",
            expected_set_operation: false,
        },
        NamesSetOperationTestCase {
            description: "a keyword after non-ASCII punctuation is found",
            sql: "select 1 «union» select 2",
            expected_set_operation: true,
        },
        NamesSetOperationTestCase {
            description: "text without a keyword is not a set operation",
            sql: "select ü, ß from t",
            expected_set_operation: false,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            names_set_operation(test_case.sql),
            test_case.expected_set_operation,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_non_ascii_characters_when_folded_then_none_matches_a_keyword_letter() {
    let test_cases = [
        KeywordFoldingTestCase {
            description: "no non-ASCII character folds to a letter of 'union'",
            keyword: "union",
            expected_non_ascii_folds: Vec::new(),
        },
        KeywordFoldingTestCase {
            description: "no non-ASCII character folds to a letter of 'intersect'",
            keyword: "intersect",
            expected_non_ascii_folds: Vec::new(),
        },
        KeywordFoldingTestCase {
            description: "no non-ASCII character folds to a letter of 'except'",
            keyword: "except",
            expected_non_ascii_folds: Vec::new(),
        },
    ];

    for test_case in test_cases {
        let folds: Vec<char> = (0x80..=0x10FFFF_u32)
            .filter_map(char::from_u32)
            .filter(|character| test_case.keyword.contains(ignorecase_key(*character)))
            .collect();

        assert_eq!(
            folds, test_case.expected_non_ascii_folds,
            "{}",
            test_case.description
        );
    }
}
