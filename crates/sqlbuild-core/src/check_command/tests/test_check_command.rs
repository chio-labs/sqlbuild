use crate::check_command::main::check_exit_code::check_exit_code;
use crate::check_command::main::check_group_label::check_group_label;
use crate::check_command::main::check_json::check_json;
use crate::check_command::main::render_check_row::render_check_row;
use crate::check_command::main::render_check_summary::render_check_summary;
use crate::check_command::main::validate_check_selection::validate_check_selection;
use crate::check_command::models::{CheckResultText, CheckRow, CheckStatus};
use crate::check_command::tests::helpers::{grouping, result};
use crate::check_command::tests::test_types::{
    GroupTestCase, RowTestCase, SelectionTestCase, SummaryTestCase,
};
use crate::cli_text::models::CliStyle;
use crate::json::models::{JsonInteger, JsonValue};

#[test]
fn given_dependencies_when_grouping_then_labels_by_single_dependency_or_group() {
    let test_cases = [
        GroupTestCase {
            description: "one dependency names the group",
            grouping: grouping(Some(&["export_orders"]), Some("declared")),
            expected_label: "export_orders",
        },
        GroupTestCase {
            description: "several dependencies use the declared group",
            grouping: grouping(Some(&["a", "b"]), Some("declared")),
            expected_label: "declared",
        },
        GroupTestCase {
            description: "several dependencies without a group are multi-dependency",
            grouping: grouping(Some(&["a", "b"]), None),
            expected_label: "multi-dependency",
        },
        GroupTestCase {
            description: "no graph and no group is ungrouped",
            grouping: grouping(None, None),
            expected_label: "ungrouped",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            check_group_label(&test_case.grouping),
            test_case.expected_label,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_row_when_rendering_then_pads_name_and_shows_detail() {
    let test_cases = [
        RowTestCase {
            description: "an error message wins over the message and warnings follow",
            row: CheckRow {
                result: CheckResultText {
                    message: Some("ignored".to_owned()),
                    error_message: Some("boom".to_owned()),
                    warning_messages: vec!["careful".to_owned()],
                    ..result("orders", CheckStatus::Fail)
                },
                duration_ms: Some(125.0),
            },
            use_color: false,
            expected_text: "  check     orders                                             FAIL  0.12s  boom\n    careful\n",
        },
        RowTestCase {
            description: "colour styles the status and an empty error falls back to the message",
            row: CheckRow {
                result: CheckResultText {
                    message: Some("fine".to_owned()),
                    error_message: Some(String::new()),
                    ..result("orders", CheckStatus::Pass)
                },
                duration_ms: None,
            },
            use_color: true,
            expected_text: "  check     orders                                             \u{1b}[32mPASS\u{1b}[0m  fine\n",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            render_check_row(
                &test_case.row,
                CliStyle {
                    use_color: test_case.use_color
                }
            ),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_results_when_summarizing_then_counts_serializes_and_exits() {
    let test_cases = [
        SummaryTestCase {
            description: "a warning does not fail the run",
            results: vec![
                CheckResultText {
                    metadata: JsonValue::Object(vec![(
                        "rows".to_owned(),
                        JsonValue::Integer(JsonInteger::from(3_i64)),
                    )]),
                    ..result("a", CheckStatus::Pass)
                },
                CheckResultText {
                    warning_messages: vec!["w".to_owned()],
                    severity: "warn".to_owned(),
                    ..result("b", CheckStatus::Warn)
                },
            ],
            expected_summary: "\nPASS=1  WARN=1  FAIL=0  TOTAL=2\n",
            expected_json: "{\n  \"version\": 1,\n  \"command\": \"check\",\n  \"status\": \"success\",\n  \
                \"summary\": {\n    \"pass_count\": 1,\n    \"warn_count\": 1,\n    \"fail_count\": 0,\n    \
                \"total_count\": 2\n  },\n  \"checks\": [\n    {\n      \"kind\": \"python_check\",\n      \
                \"name\": \"a\",\n      \"display_name\": \"a\",\n      \"check_id\": \"python_check:a\",\n      \
                \"status\": \"pass\",\n      \"passed\": true,\n      \"severity\": \"error\",\n      \
                \"message\": null,\n      \"error_message\": null,\n      \"metadata\": {\n        \
                \"rows\": 3\n      },\n      \"warnings\": null\n    },\n    {\n      \
                \"kind\": \"python_check\",\n      \"name\": \"b\",\n      \"display_name\": \"b\",\n      \
                \"check_id\": \"python_check:b\",\n      \"status\": \"warn\",\n      \"passed\": false,\n      \
                \"severity\": \"warn\",\n      \"message\": null,\n      \"error_message\": null,\n      \
                \"metadata\": {},\n      \"warnings\": [\n        \"w\"\n      ]\n    }\n  ]\n}\n",
            expected_exit_code: 0,
        },
        SummaryTestCase {
            description: "a failure fails the run",
            results: vec![result("c", CheckStatus::Fail)],
            expected_summary: "\nPASS=0  WARN=0  FAIL=1  TOTAL=1\n",
            expected_json: "{\n  \"version\": 1,\n  \"command\": \"check\",\n  \"status\": \"failed\",\n  \
                \"summary\": {\n    \"pass_count\": 0,\n    \"warn_count\": 0,\n    \"fail_count\": 1,\n    \
                \"total_count\": 1\n  },\n  \"checks\": [\n    {\n      \"kind\": \"python_check\",\n      \
                \"name\": \"c\",\n      \"display_name\": \"c\",\n      \"check_id\": \"python_check:c\",\n      \
                \"status\": \"fail\",\n      \"passed\": false,\n      \"severity\": \"error\",\n      \
                \"message\": null,\n      \"error_message\": null,\n      \"metadata\": {},\n      \
                \"warnings\": null\n    }\n  ]\n}\n",
            expected_exit_code: 1,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            (
                render_check_summary(&test_case.results, CliStyle { use_color: false }),
                check_json(&test_case.results).ok(),
                check_exit_code(&test_case.results),
            ),
            (
                test_case.expected_summary.to_owned(),
                Some(test_case.expected_json.to_owned()),
                test_case.expected_exit_code,
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_selected_names_when_validating_then_rejects_non_checks() {
    let test_cases = [
        SelectionTestCase {
            description: "only checks pass",
            non_checks: Vec::new(),
            expected_message: None,
        },
        SelectionTestCase {
            description: "non-check names are listed sorted",
            non_checks: vec!["task_b".to_owned(), "asset_a".to_owned()],
            expected_message: Some(
                "sqb check selectors must resolve only to Python checks; non-check selections: asset_a, task_b",
            ),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            validate_check_selection(&test_case.non_checks)
                .err()
                .map(|error| error.message),
            test_case.expected_message.map(str::to_owned),
            "{}",
            test_case.description
        );
    }
}
