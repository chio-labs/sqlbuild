use crate::build_progress::models::ErrorText;
use crate::cli_text::models::CliStyle;
use crate::nested_progress::main::render_nested_item::render_nested_item;
use crate::nested_progress::main::render_nested_spinner_line::render_nested_spinner_line;
use crate::nested_progress::models::{NestedChildRow, NestedItem};
use crate::nested_progress::tests::helpers::layout;
use crate::nested_progress::tests::test_types::{NestedItemTestCase, SpinnerTestCase};

const PLAIN: CliStyle = CliStyle { use_color: false };

#[test]
fn given_completed_item_when_rendering_then_draws_children_and_error_as_tree() {
    let test_cases = [
        NestedItemTestCase {
            description: "the last child closes the tree",
            item: NestedItem {
                item_name: "orders_test".to_owned(),
                status_text: "PASS".to_owned(),
                detail: "  0.10s".to_owned(),
                error: ErrorText::default(),
                child_rows: vec![NestedChildRow {
                    label: "expect".to_owned(),
                    name: "expected orders".to_owned(),
                    status_text: "PASS".to_owned(),
                    detail: String::new(),
                }],
            },
            expected_text: "    test      orders_test          PASS  0.10s\n      \u{2514}\u{2500}\u{2500} expect  expected orders  PASS\n",
        },
        NestedItemTestCase {
            description: "an error is the final tree child",
            item: NestedItem {
                item_name: "orders_test".to_owned(),
                status_text: "ERROR".to_owned(),
                detail: String::new(),
                error: ErrorText {
                    code: Some("T1".to_owned()),
                    message: Some("broken".to_owned()),
                    help: None,
                },
                child_rows: Vec::new(),
            },
            expected_text: "    test      orders_test          ERROR\n      \u{2514}\u{2500}\u{2500} error   [T1] broken\n",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            render_nested_item(&test_case.item, &layout(80), PLAIN),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_running_items_when_drawing_spinner_then_lists_and_truncates() {
    let test_cases = [
        SpinnerTestCase {
            description: "one running item is shown by name",
            running: vec!["orders_test".to_owned()],
            columns: 80,
            expected_text: "\r\x1b[K    test      orders_test          \u{280b}",
        },
        SpinnerTestCase {
            description: "several running items are counted and cut to the terminal",
            running: vec!["orders_test".to_owned(), "customers_test".to_owned()],
            columns: 30,
            expected_text: "\r\x1b[K    test      2 running:... \u{280b}",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            render_nested_spinner_line(
                &test_case.running,
                "\u{280b}",
                &layout(test_case.columns),
                PLAIN
            ),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}
