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
        CheckNameTestCase {
            description: "combining vowel sign is not alphanumeric",
            value: "\u{915}\u{93f}1",
            expected_name: "\u{915}_1",
        },
        CheckNameTestCase {
            description: "trailing combining mark is trimmed as a separator",
            value: "\u{915}\u{93f}",
            expected_name: "\u{915}",
        },
        CheckNameTestCase {
            description: "combining acute accent becomes a separator",
            value: "e\u{301}tat",
            expected_name: "e_tat",
        },
        CheckNameTestCase {
            description: "precomposed letters and Arabic-Indic digits are kept",
            value: "\u{dc}n\u{ef}c\u{f6}d\u{e9}_\u{663}\u{664}",
            expected_name: "\u{dc}n\u{ef}c\u{f6}d\u{e9}_\u{663}\u{664}",
        },
        CheckNameTestCase {
            description: "superscript, fraction and roman numeral are numeric",
            value: "x\u{b2}\u{bd}\u{216b}",
            expected_name: "x\u{b2}\u{bd}\u{216b}",
        },
        CheckNameTestCase {
            description: "ideographs and kana are kept around a separator",
            value: "\u{65e5}\u{672c}\u{8a9e}-\u{30c1}\u{30a7}\u{30c3}\u{30af}",
            expected_name: "\u{65e5}\u{672c}\u{8a9e}_\u{30c1}\u{30a7}\u{30c3}\u{30af}",
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
