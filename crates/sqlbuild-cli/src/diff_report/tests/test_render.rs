use crate::diff_report::_helpers::evidence::{
    display_example_value, render_example_pair, render_key_value,
};
use crate::diff_report::main::diff_exit_code::diff_exit_code;
use crate::diff_report::main::render_diff_error_json::render_diff_error_json;
use crate::diff_report::main::render_diff_json::render_diff_json;
use crate::diff_report::main::render_diff_text::render_diff_text;
use crate::diff_report::models::{DiffErrorFacts, DiffExampleOptions, DiffTextOptions};
use crate::diff_report::tests::helpers::{changed_rows, cursor_rows, document, model};
use crate::diff_report::tests::test_types::{
    EvidenceTestCase, JsonTestCase, KeyTestCase, OutcomeTestCase, SummaryTestCase,
};

#[test]
fn given_unequal_values_when_rendering_evidence_then_bounds_are_explicit() {
    let long = |tail: &str| format!("{}{tail}", "a".repeat(200));
    let test_cases = [
        EvidenceTestCase {
            description: "late text difference keeps nearby context",
            left: long("left-tail"),
            right: long("right-tail"),
            options: DiffExampleOptions {
                max_value_length: Some(30),
                suppress_values: false,
            },
            expected_left: "…aaaaaaaaaaaaaaaaaaaaaleft-tail [truncated; 209 chars]".to_owned(),
            expected_right: "…aaaaaaaaaaaaaaaaaaaaright-tail [truncated; 210 chars]".to_owned(),
            expected_first_difference: Some(200),
        },
        EvidenceTestCase {
            description: "suppression retains lengths without values",
            left: "left-private-value".to_owned(),
            right: "right-private-value".to_owned(),
            options: DiffExampleOptions {
                max_value_length: Some(30),
                suppress_values: true,
            },
            expected_left: "<value suppressed; 18 chars>".to_owned(),
            expected_right: "<value suppressed; 19 chars>".to_owned(),
            expected_first_difference: Some(0),
        },
        EvidenceTestCase {
            description: "explicit unlimited rendering preserves complete values",
            left: long("left-tail"),
            right: long("right-tail"),
            options: DiffExampleOptions {
                max_value_length: None,
                suppress_values: false,
            },
            expected_left: long("left-tail"),
            expected_right: long("right-tail"),
            expected_first_difference: Some(200),
        },
    ];

    for test_case in test_cases {
        let (left, right) =
            render_example_pair(&test_case.left, &test_case.right, test_case.options);

        assert_eq!(
            (
                display_example_value(&left),
                display_example_value(&right),
                left.first_difference,
            ),
            (
                test_case.expected_left,
                test_case.expected_right,
                test_case.expected_first_difference,
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_keys_when_rendering_then_long_keys_are_shortened_with_their_digest() {
    let test_cases = [
        KeyTestCase {
            description: "ordinary key stays complete",
            key: "k".repeat(256),
            expected_prefix: "k".repeat(256),
            expected_suffix: String::new(),
        },
        KeyTestCase {
            description: "long key names its length and digest",
            key: "k".repeat(300),
            expected_prefix: format!("{}… [truncated; 300 chars; sha256:", "k".repeat(256)),
            expected_suffix: "]".to_owned(),
        },
    ];

    for test_case in test_cases {
        let rendered: String = render_key_value(&test_case.key);

        assert_eq!(
            (
                rendered.starts_with(&test_case.expected_prefix),
                rendered.ends_with(&test_case.expected_suffix),
            ),
            (true, true),
            "{}: {rendered}",
            test_case.description
        );
    }
}

#[test]
fn given_results_when_resolving_outcome_then_exit_code_matches() {
    let test_cases = [
        OutcomeTestCase {
            description: "identical rows pass",
            models: vec![model(Some(changed_rows(0)), &[])],
            query_row_comparison: false,
            expected_outcome: ("pass", 0),
        },
        OutcomeTestCase {
            description: "unequal rows are findings",
            models: vec![model(Some(changed_rows(1)), &[])],
            query_row_comparison: false,
            expected_outcome: ("findings", 1),
        },
        OutcomeTestCase {
            description: "query schema change without row comparison is incomplete",
            models: vec![model(None, &["extra"])],
            query_row_comparison: true,
            expected_outcome: ("incomplete", 2),
        },
        OutcomeTestCase {
            description: "model schema change is a finding",
            models: vec![model(None, &["extra"])],
            query_row_comparison: false,
            expected_outcome: ("findings", 1),
        },
    ];

    for test_case in test_cases {
        let (outcome, code) = diff_exit_code(&test_case.models, test_case.query_row_comparison);

        assert_eq!(
            (outcome.as_str(), code),
            test_case.expected_outcome,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_changed_rows_when_rendering_summary_then_layout_matches_rich() {
    let test_cases = [SummaryTestCase {
        description: "one unequal row",
        model: model(Some(changed_rows(1)), &[]),
        expected_lines: &[
            "     Model  orders                   ",
            "┏━┯━┯━┯━┯━┓╌╌╌┏━┯━┯━┯━┯━┓╭──┬──────────┬─────────╮╌╮            ",
            "┃ │ │ │ │ ┃ ≠ ┃ │ │ │ │ ┃│ 2│ equal    │ (66.67%)│ │            ",
            "│ amount │ mismatches=1 │ match=66.67% │",
        ],
    }];

    for test_case in test_cases {
        let text: String = render_diff_text(
            &[test_case.model],
            &document(),
            &DiffTextOptions {
                mode_label: "full".to_owned(),
                max_column_examples: 3,
                max_row_only_examples: 3,
                ..DiffTextOptions::default()
            },
        );

        let rendered: Vec<&str> = text.lines().collect();
        let found: Vec<&str> = test_case
            .expected_lines
            .iter()
            .copied()
            .filter(|line| rendered.contains(line))
            .collect();

        assert_eq!(
            found,
            test_case.expected_lines.to_vec(),
            "{}: {text}",
            test_case.description
        );
    }
}

#[test]
fn given_results_when_rendering_json_then_documents_are_sorted_and_safe() {
    let test_cases = [
        JsonTestCase {
            description: "non-finite cursor bound becomes a tagged object",
            document: render_diff_json(&[model(Some(cursor_rows()), &[])], &document()),
            expected_fragment: "\"start\": {\n            \"kind\": \"non_finite_number\",\n            \"value\": \"NaN\"\n          }",
        },
        JsonTestCase {
            description: "error document keeps the incomplete outcome",
            document: render_diff_error_json(&DiffErrorFacts {
                status: "incomplete".to_owned(),
                code: "C254".to_owned(),
                message: "key is not unique".to_owned(),
                help: None,
                size_guard: None,
            }),
            expected_fragment: "{\n  \"error\": {\n    \"code\": \"C254\",\n    \"message\": \"key is not unique\"\n  },\n  \"models\": [],\n  \"outcome\": \"incomplete\",\n  \"query_comparisons\": [],\n  \"schema_version\": 1,\n  \"status\": \"incomplete\"\n}",
        },
    ];

    for test_case in test_cases {
        let text: String = test_case.document.unwrap_or_default();

        assert!(
            text.contains(test_case.expected_fragment),
            "{}: {text}",
            test_case.description
        );
    }
}
