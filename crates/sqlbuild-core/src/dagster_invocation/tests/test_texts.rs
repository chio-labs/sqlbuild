//! Check names, log lines and failure text match the Dagster integration's output.

use crate::dagster_invocation::main::asset_failure_text::asset_failure_text;
use crate::dagster_invocation::main::normalize_check_name::normalize_check_name;
use crate::dagster_invocation::main::wrap_selectors::wrap_selectors;
use crate::dagster_invocation::models::AssetFailure;
use crate::dagster_invocation::tests::test_types::{
    CheckNameTestCase, FailureTextTestCase, WrapTestCase,
};

#[test]
fn given_raw_check_name_when_normalizing_then_replaces_punctuation() {
    let test_cases = [
        CheckNameTestCase {
            description: "punctuation becomes separators",
            value: "not_null(order-id)",
            expected_name: "not_null_order_id",
        },
        CheckNameTestCase {
            description: "only punctuation falls back",
            value: "--",
            expected_name: "check",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            normalize_check_name(test_case.value),
            test_case.expected_name,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_selectors_when_wrapping_then_packs_lines_within_width() {
    let test_cases = [WrapTestCase {
        description: "long selector stands alone",
        selectors: vec!["orders", "customers", "a_very_long_selector_name"],
        width: 16,
        expected_lines: vec!["orders customers", "a_very_long_selector_name"],
    }];
    for test_case in test_cases {
        let selectors: Vec<String> = test_case
            .selectors
            .iter()
            .map(|selector| (*selector).to_owned())
            .collect();
        assert_eq!(
            wrap_selectors(&selectors, test_case.width),
            test_case.expected_lines,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_failed_asset_when_formatting_then_lists_error_relation_and_sql() {
    let test_cases = [FailureTextTestCase {
        description: "every detail",
        failure: AssetFailure {
            kind: "model".to_owned(),
            name: "orders".to_owned(),
            status: "failed".to_owned(),
            failed_phase: Some("execute".to_owned()),
            error_message: Some("boom".to_owned()),
            error_code: Some("X100".to_owned()),
            staging_relation: Some("main.orders__staging".to_owned()),
            failed_sql: Some("SELECT 1\n\nFROM t".to_owned()),
            last_recorded_sql: None,
        },
        expected_text: "model:orders (failed) during execute\n  [X100] boom\n  staging relation: main.orders__staging\n  failed SQL:\n    SELECT 1\n\n    FROM t",
    }];
    for test_case in test_cases {
        assert_eq!(
            asset_failure_text(&test_case.failure),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}
