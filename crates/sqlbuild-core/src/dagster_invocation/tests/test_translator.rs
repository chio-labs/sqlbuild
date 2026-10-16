//! The default Dagster translator's names and descriptions match its Python spelling.

use crate::dagster_invocation::main::asset_description::asset_description;
use crate::dagster_invocation::main::dagster_name_segment::dagster_name_segment;
use crate::dagster_invocation::main::dagster_tag_key::dagster_tag_key;
use crate::dagster_invocation::main::fallback_asset_description::fallback_asset_description;
use crate::dagster_invocation::tests::test_types::{
    DescriptionTestCase, FallbackDescriptionTestCase, NameNormalizationTestCase,
};

#[test]
fn given_tags_and_names_when_normalized_then_rejected_runs_become_one_separator() {
    let test_cases = [
        NameNormalizationTestCase {
            description: "a plain name",
            value: "pii",
            expected_tag_key: "pii",
            expected_segment: "pii",
        },
        NameNormalizationTestCase {
            description: "punctuation runs collapse",
            value: "a b!c",
            expected_tag_key: "a_b_c",
            expected_segment: "a_b_c",
        },
        NameNormalizationTestCase {
            description: "outer separators are trimmed",
            value: "__x__",
            expected_tag_key: "x",
            expected_segment: "x",
        },
        NameNormalizationTestCase {
            description: "non-ASCII letters are rejected",
            value: "\u{65e5}\u{672c}",
            expected_tag_key: "",
            expected_segment: "check",
        },
        NameNormalizationTestCase {
            description: "tag keys keep dots, dashes and slashes",
            value: "ok/x.y-z",
            expected_tag_key: "ok/x.y-z",
            expected_segment: "ok_x_y_z",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            (
                dagster_tag_key(test_case.value),
                dagster_name_segment(test_case.value)
            ),
            (
                test_case.expected_tag_key.to_owned(),
                test_case.expected_segment.to_owned()
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_node_text_when_described_then_sql_wins_over_the_source_file() {
    let test_cases = [
        DescriptionTestCase {
            description: "stripped SQL is fenced",
            text: "D",
            sql: Some("  select 1  "),
            path: Some("m.sql"),
            expected_description: "D\n\n**SQLBuild SQL:**\n```sql\nselect 1\n```",
        },
        DescriptionTestCase {
            description: "blank SQL falls back to the source file",
            text: "D",
            sql: Some("   "),
            path: Some("m.sql"),
            expected_description: "D\n\n**Source file:** `m.sql`",
        },
        DescriptionTestCase {
            description: "backticks in the path widen the fence",
            text: "D",
            sql: None,
            path: Some("a`b`` c.py"),
            expected_description: "D\n\n**Source file:** ```a`b`` c.py```",
        },
        DescriptionTestCase {
            description: "an edge backtick pads the span",
            text: "D",
            sql: None,
            path: Some("`start"),
            expected_description: "D\n\n**Source file:** `` `start ``",
        },
        DescriptionTestCase {
            description: "no SQL or path keeps the text",
            text: "D",
            sql: None,
            path: Some(""),
            expected_description: "D",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            asset_description(test_case.text, test_case.sql, test_case.path),
            test_case.expected_description,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_undocumented_node_when_described_then_kind_name_and_relation_are_named() {
    let test_cases = [
        FallbackDescriptionTestCase {
            description: "a materialized relation",
            kind: "python_asset",
            name: "o",
            qualified_name: "db.o",
            materialization: Some("table"),
            expected_description: "SQLBuild python asset `o` materialized as `table` at `db.o`.",
        },
        FallbackDescriptionTestCase {
            description: "no relation or materialization",
            kind: "seed",
            name: "s",
            qualified_name: "",
            materialization: None,
            expected_description: "SQLBuild seed `s`.",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            fallback_asset_description(
                test_case.kind,
                test_case.name,
                test_case.qualified_name,
                test_case.materialization
            ),
            test_case.expected_description,
            "{}",
            test_case.description
        );
    }
}
