use crate::refactoring::_helpers::chars::chars;
use crate::refactoring::_helpers::text_edits::{
    file_changes, identifier_sites, line_column, text_edit, whole_word_offsets,
};
use crate::refactoring::models::EditKind;
use crate::refactoring::tests::helpers::applied;
use crate::refactoring::tests::test_types::{ApplyEditsTestCase, IdentifierSitesTestCase};

#[test]
fn given_edits_when_applying_then_python_order_and_overlap_rules_hold() {
    let test_cases = [
        ApplyEditsTestCase {
            description: "disjoint edits apply back to front",
            text: "SELECT a FROM t",
            edits: &[(7, 8, "b"), (14, 15, "u")],
            expected: Ok("SELECT b FROM u"),
        },
        ApplyEditsTestCase {
            description: "identical duplicates apply once",
            text: "SELECT a FROM t",
            edits: &[(7, 8, "b"), (7, 8, "b")],
            expected: Ok("SELECT b FROM t"),
        },
        ApplyEditsTestCase {
            description: "overlapping edits are refused at the earlier edit",
            text: "SELECT abc FROM t",
            edits: &[(7, 10, "x"), (9, 12, "y")],
            expected: Err("overlapping refactoring edits at offset 7"),
        },
        ApplyEditsTestCase {
            description: "two insertions at one offset keep Python's stable reverse order",
            text: "x",
            edits: &[(0, 0, "A"), (0, 0, "B")],
            expected: Ok("BAx"),
        },
        ApplyEditsTestCase {
            description: "offsets count code points",
            text: "é a",
            edits: &[(2, 3, "b")],
            expected: Ok("é b"),
        },
    ];
    for test_case in test_cases {
        let text = chars(test_case.text);
        let edits: Vec<_> = test_case
            .edits
            .iter()
            .map(|(start, end, replacement)| {
                text_edit(
                    &text,
                    (*start, *end),
                    (*replacement).to_owned(),
                    EditKind::Reference,
                    (None, None),
                )
            })
            .collect();
        let result = applied(test_case.text, &edits).map_err(|error| error.message);
        assert_eq!(
            result,
            test_case.expected.map(str::to_owned).map_err(str::to_owned),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_text_when_finding_identifier_sites_then_code_is_matched_ignoring_case() {
    let test_cases = [
        IdentifierSitesTestCase {
            description: "comments and strings are skipped, case is ignored",
            text: "WITH __ref__orders AS (SELECT 1) SELECT * FROM __REF__ORDERS -- __ref__orders\n'__ref__orders'",
            names: &["__ref__orders"],
            expected_sites: &[(5, 18, "__ref__orders"), (47, 60, "__ref__orders")],
        },
        IdentifierSitesTestCase {
            description: "the longest name wins",
            text: "x __ref__orders_v2 y",
            names: &["__ref__orders", "__ref__orders_v2"],
            expected_sites: &[(2, 18, "__ref__orders_v2")],
        },
        IdentifierSitesTestCase {
            description: "a name inside a longer identifier is not a site",
            text: "a__ref__orders $__ref__orders __ref__orders$",
            names: &["__ref__orders"],
            expected_sites: &[],
        },
    ];
    for test_case in test_cases {
        let names: Vec<String> = test_case
            .names
            .iter()
            .map(|name| (*name).to_owned())
            .collect();
        let sites = identifier_sites(&chars(test_case.text), &names);
        let expected: Vec<(usize, usize, String)> = test_case
            .expected_sites
            .iter()
            .map(|(start, end, name)| (*start, *end, (*name).to_owned()))
            .collect();
        assert_eq!(sites, expected, "{}", test_case.description);
    }
}

#[test]
fn given_text_when_finding_whole_words_then_identifier_neighbours_are_excluded() {
    assert_eq!(
        whole_word_offsets(&chars("amount, AMOUNT_total, x.amount"), "amount"),
        vec![0, 24]
    );
}

#[test]
fn given_offset_when_locating_then_line_and_column_are_one_based() {
    assert_eq!(line_column(&chars("ab\ncd"), 4), (2, 2));
    assert_eq!(line_column(&chars("ab\ncd"), 0), (1, 1));
}

#[test]
fn given_edits_and_moves_when_grouping_then_changes_follow_final_paths() {
    let text = chars("abc");
    let edit = text_edit(
        &text,
        (0, 1),
        "x".to_owned(),
        EditKind::Reference,
        (None, None),
    );
    let changes = file_changes(
        vec![
            ("models/b.sql".to_owned(), edit.clone()),
            ("models/a.sql".to_owned(), edit),
        ],
        &[("models/b.sql".to_owned(), "models/z/b.sql".to_owned())],
    );
    let paths: Vec<(&str, &str, usize)> = changes
        .iter()
        .map(|change| {
            (
                change.path.as_str(),
                change.original_path.as_str(),
                change.edits.len(),
            )
        })
        .collect();
    assert_eq!(
        paths,
        vec![
            ("models/a.sql", "models/a.sql", 1),
            ("models/z/b.sql", "models/b.sql", 1)
        ]
    );
}
