use std::collections::BTreeSet;

use crate::cli_text::models::CliStyle;
use crate::clone_text::_helpers::quoted::clone_relation_display_name;
use crate::clone_text::main::clone_exit_code::clone_exit_code;
use crate::clone_text::main::render_clone_completion::render_clone_completion;
use crate::clone_text::main::render_clone_fingerprint_interrupted_line::render_clone_fingerprint_interrupted_line;
use crate::clone_text::main::render_clone_fingerprint_progress_line::render_clone_fingerprint_progress_line;
use crate::clone_text::main::render_clone_item_line::render_clone_item_line;
use crate::clone_text::main::validate_clone_policy::validate_clone_policy;
use crate::clone_text::main::validate_clone_target_names::validate_clone_target_names;
use crate::clone_text::models::{CloneItemText, CloneStatusKind, FingerprintProgress};
use crate::clone_text::tests::helpers::{item, pending_identities, with_message};
use crate::clone_text::tests::test_types::{
    CompletionTestCase, DisplayNameTestCase, FingerprintTestCase, ItemLineTestCase, TargetTestCase,
};

#[test]
fn given_relation_when_displaying_then_lowercases_only_unquoted_parts() {
    let test_cases = [
        DisplayNameTestCase {
            description: "plain identifiers are lowercased",
            relation: "PROD.Fact_Orders",
            expected_name: "prod.fact_orders",
        },
        DisplayNameTestCase {
            description: "double, backtick and bracket quotes keep their case",
            relation: "DB.\"Mixed\"\"Case\".`Tick`.[Br]]ack]",
            expected_name: "db.\"Mixed\"\"Case\".`Tick`.[Br]]ack]",
        },
        DisplayNameTestCase {
            description: "an unclosed quote is ordinary text",
            relation: "A.\"Open",
            expected_name: "a.\"open",
        },
        DisplayNameTestCase {
            description: "a trailing doubled quote backtracks to the first closing quote",
            relation: "\"Ab\"\"C",
            expected_name: "\"Ab\"\"c",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            clone_relation_display_name(test_case.relation),
            test_case.expected_name,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_item_when_rendering_line_then_aligns_action_and_relations() {
    let test_cases = [
        ItemLineTestCase {
            description: "relations, duration and padding to the widest flow",
            position: (2, 12),
            item: CloneItemText {
                origin_relation: Some("PROD.Orders".to_owned()),
                destination_relation: Some("dev.orders".to_owned()),
                duration_seconds: Some(0.125),
                ..item("orders", "copied", CloneStatusKind::Success)
            },
            relation_width: 30,
            use_color: false,
            expected_line: "   2/12  copied                      prod.orders -> dev.orders       OK  0.12s",
        },
        ItemLineTestCase {
            description: "quoted identifiers keep their case in the flow",
            position: (5, 5),
            item: CloneItemText {
                origin_relation: Some("PROD.DBO.[My]]Table]".to_owned()),
                destination_relation: Some("DEV.MAIN.\"Orders\"".to_owned()),
                ..item("orders", "cloned", CloneStatusKind::Success)
            },
            relation_width: 0,
            use_color: false,
            expected_line: "  5/5  cloned                      prod.dbo.[My]]Table] -> dev.main.\"Orders\"  OK",
        },
        ItemLineTestCase {
            description: "missing relations fall back to the lowercased name",
            position: (1, 1),
            item: item("Stg", "warning_missing_source", CloneStatusKind::Warning),
            relation_width: 0,
            use_color: false,
            expected_line: "  1/1  warning_missing_source      stg  WARN",
        },
        ItemLineTestCase {
            description: "colour styles position, action, arrow and status",
            position: (1, 1),
            item: CloneItemText {
                origin_relation: Some("a.x".to_owned()),
                destination_relation: Some("b.x".to_owned()),
                ..item("x", "failed", CloneStatusKind::Failed)
            },
            relation_width: 0,
            use_color: true,
            expected_line: "  \u{1b}[2m1/1\u{1b}[0m  \u{1b}[34mfailed\u{1b}[0m                      a.x \u{1b}[2m->\u{1b}[0m b.x  \u{1b}[38;5;167mFAIL\u{1b}[0m",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            render_clone_item_line(
                test_case.position,
                &test_case.item,
                test_case.relation_width,
                CliStyle {
                    use_color: test_case.use_color
                },
            ),
            test_case.expected_line,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_items_when_completing_then_reports_messages_counts_and_exit_code() {
    let test_cases = [
        CompletionTestCase {
            description: "a failure reports errors and messages of non-success items",
            items: vec![
                item("fact_orders", "cloned", CloneStatusKind::Success),
                with_message(
                    item(
                        "stg_orders",
                        "warning_missing_source",
                        CloneStatusKind::Warning,
                    ),
                    "missing in origin environment",
                ),
                with_message(
                    item("dim_customers", "failed", CloneStatusKind::Failed),
                    "boom",
                ),
                with_message(
                    item("add_tax", "recreated_function", CloneStatusKind::Success),
                    "ignored",
                ),
            ],
            elapsed_seconds: None,
            use_color: false,
            expected_text: "  stg_orders  missing in origin environment\n  dim_customers  boom\n\n\
                \u{2717} Completed with errors  CLONED=1  COPIED=0  RECREATED_VIEWS=0  \
                RECREATED_FUNCTIONS=1  PASS=2  WARN=1  FAIL=1  TOTAL=4\n",
            expected_exit_code: 1,
        },
        CompletionTestCase {
            description: "success shows the elapsed time in one pair of parentheses",
            items: vec![item("orders", "copied", CloneStatusKind::Success)],
            elapsed_seconds: Some(1.5),
            use_color: false,
            expected_text: "\n\u{2713} Completed successfully  CLONED=0  COPIED=1  RECREATED_VIEWS=0  \
                RECREATED_FUNCTIONS=0  PASS=1  WARN=0  FAIL=0  TOTAL=1  (1.50s)\n",
            expected_exit_code: 0,
        },
        CompletionTestCase {
            description: "colour styles the failure glyph and label",
            items: vec![item("orders", "failed", CloneStatusKind::Failed)],
            elapsed_seconds: None,
            use_color: true,
            expected_text: "\n\u{1b}[38;5;167m\u{2717}\u{1b}[0m \u{1b}[38;5;167m\u{1b}[1mCompleted with errors\u{1b}[0m  \
                \u{1b}[2mCLONED=\u{1b}[0m\u{1b}[34m0\u{1b}[0m  \u{1b}[2mCOPIED=\u{1b}[0m\u{1b}[34m0\u{1b}[0m  \
                \u{1b}[2mRECREATED_VIEWS=\u{1b}[0m\u{1b}[34m0\u{1b}[0m  \
                \u{1b}[2mRECREATED_FUNCTIONS=\u{1b}[0m\u{1b}[34m0\u{1b}[0m  \
                \u{1b}[2mPASS=\u{1b}[0m\u{1b}[32m0\u{1b}[0m  \u{1b}[2mWARN=\u{1b}[0m\u{1b}[33m0\u{1b}[0m  \
                \u{1b}[2mFAIL=\u{1b}[0m\u{1b}[38;5;167m1\u{1b}[0m  \u{1b}[2mTOTAL=\u{1b}[0m\u{1b}[34m1\u{1b}[0m\n",
            expected_exit_code: 1,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            (
                render_clone_completion(
                    &test_case.items,
                    test_case.elapsed_seconds,
                    CliStyle {
                        use_color: test_case.use_color
                    },
                ),
                clone_exit_code(&test_case.items),
            ),
            (
                test_case.expected_text.to_owned(),
                test_case.expected_exit_code
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_fingerprint_progress_when_rendering_then_reports_confirmed_and_pending() {
    let test_cases = [
        FingerprintTestCase {
            description: "progress pads the count and interruption bounds pending identities",
            progress: FingerprintProgress {
                completed: 50,
                total: 386,
                pending_identities: pending_identities(),
            },
            expected_progress_line: "  fingerprint[ 50/386] propagated OK",
            expected_interrupted_line: Some(
                "  fingerprint[50/386] FAIL not confirmed: model:orders_0, \
                model:orders_1, model:orders_2, model:orders_3, model:orders_4, model:orders_5, \
                model:orders_6, model:orders_7, model:orders_8, model:orders_9 (+2 more)",
            ),
        },
        FingerprintTestCase {
            description: "a fully confirmed propagation reports no interruption",
            progress: FingerprintProgress {
                completed: 3,
                total: 3,
                pending_identities: Vec::new(),
            },
            expected_progress_line: "  fingerprint[3/3] propagated OK",
            expected_interrupted_line: None,
        },
    ];

    for test_case in test_cases {
        let style: CliStyle = CliStyle { use_color: false };
        assert_eq!(
            (
                render_clone_fingerprint_progress_line(
                    test_case.progress.completed,
                    test_case.progress.total,
                    style,
                ),
                render_clone_fingerprint_interrupted_line(&test_case.progress, style),
            ),
            (
                test_case.expected_progress_line.to_owned(),
                test_case.expected_interrupted_line.map(str::to_owned),
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_targets_when_validating_then_reports_the_first_problem() {
    let known: BTreeSet<String> = ["dev", "prod"].into_iter().map(str::to_owned).collect();
    let test_cases = [
        TargetTestCase {
            description: "known distinct targets with allowed policies pass",
            targets: ("prod", "dev"),
            policy: (true, true),
            expected_codes: (None, None),
        },
        TargetTestCase {
            description: "the same target is rejected first",
            targets: ("dev", "dev"),
            policy: (true, true),
            expected_codes: (Some("C401"), None),
        },
        TargetTestCase {
            description: "unknown origin",
            targets: ("nope", "dev"),
            policy: (false, true),
            expected_codes: (Some("C402"), Some("C404")),
        },
        TargetTestCase {
            description: "unknown destination and denied destination policy",
            targets: ("prod", "nope"),
            policy: (true, false),
            expected_codes: (Some("C403"), Some("C405")),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            (
                validate_clone_target_names(test_case.targets, &known)
                    .err()
                    .map(|error| error.code),
                validate_clone_policy(test_case.targets, test_case.policy)
                    .err()
                    .map(|error| error.code),
            ),
            test_case.expected_codes,
            "{}",
            test_case.description
        );
    }
}
