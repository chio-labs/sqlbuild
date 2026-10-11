use crate::compiled_project::main::enum_member_literal::enum_member_literal;
use crate::compiled_project::main::merge_call_site_references::merge_call_site_references;
use crate::compiled_project::main::splice_declarations::splice_declarations;
use crate::compiled_project::tests::helpers::splice;
use crate::compiled_project::tests::test_types::{
    EnumLiteralTestCase, MergeReferencesTestCase, SpliceTestCase,
};

#[test]
fn given_scanned_references_when_splicing_then_character_ranges_are_kept() {
    let test_cases = [
        SpliceTestCase {
            description: "two references",
            sql: "SELECT @enum.status.open, @const.limit",
            splices: vec![splice(7, 24, "'open'"), splice(26, 38, "10")],
            expected_sql: "SELECT 'open', 10",
            expected_output_ranges: vec![(7, 13), (15, 17)],
        },
        SpliceTestCase {
            description: "multi-byte text before a reference",
            sql: "SELECT 'é', @const.limit",
            splices: vec![splice(12, 24, "'ü'")],
            expected_sql: "SELECT 'é', 'ü'",
            expected_output_ranges: vec![(12, 15)],
        },
    ];

    for test_case in test_cases {
        let spliced = splice_declarations(test_case.sql, &test_case.splices);
        let ranges: Vec<(usize, usize)> = spliced
            .spans
            .iter()
            .map(|span| (span.output_start, span.output_end))
            .collect();

        assert_eq!(
            spliced.sql, test_case.expected_sql,
            "{}",
            test_case.description
        );
        assert_eq!(
            ranges, test_case.expected_output_ranges,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_enum_member_when_rendering_then_text_is_quoted_and_integers_are_bare() {
    let test_cases = [
        EnumLiteralTestCase {
            description: "text member",
            text: "it's",
            integer: false,
            expected_literal: "'it''s'",
        },
        EnumLiteralTestCase {
            description: "integer member",
            text: "42",
            integer: true,
            expected_literal: "42",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            enum_member_literal(test_case.text, test_case.integer),
            test_case.expected_literal,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_macro_argument_references_when_merging_then_each_reference_appears_once() {
    let test_cases = [
        MergeReferencesTestCase {
            description: "no arguments keep scanned duplicates",
            references: vec!["orders", "orders"],
            arguments: vec![],
            expected_references: vec!["orders", "orders"],
        },
        MergeReferencesTestCase {
            description: "arguments deduplicate the whole list in first-seen order",
            references: vec!["orders", "orders", "customers"],
            arguments: vec!["payments", "customers"],
            expected_references: vec!["orders", "customers", "payments"],
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            merge_call_site_references(test_case.references, test_case.arguments),
            test_case.expected_references,
            "{}",
            test_case.description
        );
    }
}
