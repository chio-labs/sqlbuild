use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::ceremonial_select::main::omitted_select_offset::omitted_select_offset;
use crate::ceremonial_select::models::OmittedSelect;
use crate::ceremonial_select::tests::test_types::OmittedSelectTestCase;

#[test]
fn given_test_bodies_when_locating_omitted_select_then_python_offset_is_returned() {
    let test_cases = [
        OmittedSelectTestCase {
            description: "a body ending after its last CTE gets the offset after `)`",
            sql: "with a AS (SELECT 'é)') ;\n",
            expected_offset: OmittedSelect::At(23),
        },
        OmittedSelectTestCase {
            description: "a trailing comment after the last CTE",
            sql: "WITH a AS (SELECT 1) -- done",
            expected_offset: OmittedSelect::At(20),
        },
        OmittedSelectTestCase {
            description: "a body with its ceremonial SELECT is unchanged",
            sql: "WITH a AS (SELECT 1) SELECT 1",
            expected_offset: OmittedSelect::Absent,
        },
        OmittedSelectTestCase {
            description: "a body that is not a WITH statement",
            sql: "WITHIN (1)",
            expected_offset: OmittedSelect::Absent,
        },
        OmittedSelectTestCase {
            description: "an unclosed quote is not completed",
            sql: "WITH a AS (SELECT ')') '",
            expected_offset: OmittedSelect::Absent,
        },
        OmittedSelectTestCase {
            description: "non-ASCII keyword text defers to Python's case mapping",
            sql: "w\u{131}th a AS (SELECT 1)",
            expected_offset: OmittedSelect::Deferred,
        },
    ];

    for test_case in test_cases {
        let syntax: LexicalSyntax = LexicalSyntax {
            line_comment_prefixes: vec!["--".to_owned()],
            ..LexicalSyntax::default()
        };
        assert_eq!(
            omitted_select_offset(test_case.sql, &syntax),
            test_case.expected_offset,
            "{}",
            test_case.description
        );
    }
}
