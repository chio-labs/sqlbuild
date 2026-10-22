use crate::cli_text::models::CliStyle;
use crate::dbt_events::main::format_dbt_active_nodes::format_dbt_active_nodes;
use crate::dbt_events::main::render_dbt_node_row::render_dbt_node_row;
use crate::dbt_events::models::{
    DbtEvent, DbtNodeMessage, DbtNodeResult, DbtRowPosition, DbtStreamUpdate,
};
use crate::dbt_events::tests::helpers::{
    event, finished, message_event, result_event, started, updates,
};
use crate::dbt_events::tests::test_types::{StreamTestCase, TextTestCase};

const PLAIN: CliStyle = CliStyle { use_color: false };

#[test]
fn given_dbt_events_when_consuming_then_reports_starts_and_first_results() {
    let test_cases = [
        StreamTestCase {
            description: "a start row, its result at the same counter, then a duplicate",
            events: vec![
                event("NodeStarted", "model.a.orders"),
                event("NodeStarted", "model.a.orders"),
                result_event("LogModelResult", "model.a.orders", "SELECT 1"),
                result_event("NodeFinished", "model.a.orders", "success"),
            ],
            expected_updates: vec![
                started("model.a.orders", 1),
                Some(DbtStreamUpdate {
                    row: None,
                    ..started("model.a.orders", 1).unwrap_or_default()
                }),
                finished("model.a.orders", ("unknown", 1), Vec::new()),
                None,
            ],
        },
        StreamTestCase {
            description: "buffered messages attach to the result and other lines are ignored",
            events: vec![
                message_event("model.a.customers", "  relation missing \n"),
                DbtEvent::default(),
                event("FoundStats", "model.a.customers"),
                result_event("LogModelResult", "model.a.customers", "ERROR"),
            ],
            expected_updates: vec![
                None,
                None,
                None,
                finished(
                    "model.a.customers",
                    ("ERROR", 1),
                    vec![DbtNodeMessage {
                        level: "error".to_owned(),
                        message: "relation missing".to_owned(),
                    }],
                ),
            ],
        },
        StreamTestCase {
            description: "an error-level result with a message still streams its row",
            events: vec![
                message_event("model.a.payments", "relation missing"),
                DbtEvent {
                    level: Some("error".to_owned()),
                    info_msg: Some("1 of 2 ERROR creating table model payments".to_owned()),
                    ..result_event("LogModelResult", "model.a.payments", "ERROR")
                },
            ],
            expected_updates: vec![
                None,
                finished(
                    "model.a.payments",
                    ("ERROR", 1),
                    vec![
                        DbtNodeMessage {
                            level: "error".to_owned(),
                            message: "relation missing".to_owned(),
                        },
                        DbtNodeMessage {
                            level: "error".to_owned(),
                            message: "1 of 2 ERROR creating table model payments".to_owned(),
                        },
                    ],
                ),
            ],
        },
        StreamTestCase {
            description: "a warn-level test result keeps its own message",
            events: vec![DbtEvent {
                level: Some("warn".to_owned()),
                info_msg: Some("FAIL 3 not_null_orders_id".to_owned()),
                ..result_event("LogTestResult", "test.a.not_null_orders_id", "fail")
            }],
            expected_updates: vec![finished(
                "test.a.not_null_orders_id",
                ("fail", 1),
                vec![DbtNodeMessage {
                    level: "warn".to_owned(),
                    message: "FAIL 3 not_null_orders_id".to_owned(),
                }],
            )],
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            updates(&test_case.events),
            test_case.expected_updates,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_node_rows_when_rendering_then_writes_aligned_rows_and_progress() {
    let result: DbtNodeResult = DbtNodeResult {
        unique_id: "model.a.orders".to_owned(),
        resource_type: "incremental_model".to_owned(),
        node_name: "orders".to_owned(),
        status: "success".to_owned(),
        index: Some(3),
        total: Some(9),
        execution_time: Some(1.005),
        messages: vec![DbtNodeMessage {
            level: "warn".to_owned(),
            message: "slow".to_owned(),
        }],
        ..DbtNodeResult::default()
    };
    let test_cases = [
        TextTestCase {
            description: "dbt counter, truncated type, duration and message",
            rendered: render_dbt_node_row(&result, DbtRowPosition::default(), "", PLAIN),
            expected_text: "  3/9   increment orders                         OK     1.00s\n         warn      slow\n",
        },
        TextTestCase {
            description: "stream counter and detail without timing",
            rendered: render_dbt_node_row(
                &DbtNodeResult {
                    execution_time: None,
                    messages: Vec::new(),
                    status: "start".to_owned(),
                    ..result.clone()
                },
                DbtRowPosition {
                    display_index: Some(2),
                    display_total: Some(4),
                },
                "defer",
                PLAIN,
            ),
            expected_text: "  2/4   increment orders                         START         defer\n",
        },
        TextTestCase {
            description: "longest-running nodes first, with the rest counted",
            rendered: format_dbt_active_nodes(
                &[
                    ("c".to_owned(), 9.5),
                    ("a".to_owned(), 1.0),
                    ("b".to_owned(), 5.0),
                    ("d".to_owned(), 9.9),
                ],
                10.0,
            ),
            expected_text: "running 4 dbt nodes: a 9s, b 5s, c <1s, +1 more",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            test_case.rendered, test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}
