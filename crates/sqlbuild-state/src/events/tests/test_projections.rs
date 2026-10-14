use crate::events::main::newest_column_event::newest_column_event;
use crate::events::main::newest_move_event::newest_move_event;
use crate::events::main::old_name_histories::old_name_histories;
use crate::events::models::{OldNameHistoryIndexes, OldNameStep};
use crate::events::tests::helpers::{fact, moved, order, relation, renamed};
use crate::events::tests::test_types::{HistoryTestCase, NewestColumnTestCase, NewestMoveTestCase};

#[test]
fn given_moves_when_projecting_newest_mention_then_latest_first_tied_event_wins() {
    let test_cases = [
        NewestMoveTestCase {
            description: "later event wins by time",
            events: vec![
                moved(order(2, "a"), ("orders", "orders_v2")),
                moved(order(1, "z"), ("orders_v2", "orders")),
            ],
            relation: relation(None, "MAIN", "Orders"),
            expected_index: Some(0),
        },
        NewestMoveTestCase {
            description: "equal times order by event ID",
            events: vec![
                moved(order(1, "b"), ("orders", "x")),
                moved(order(1, "a"), ("x", "orders")),
            ],
            relation: relation(Some("db"), "main", "orders"),
            expected_index: Some(0),
        },
        NewestMoveTestCase {
            description: "identical orders keep the first",
            events: vec![
                moved(order(1, "a"), ("orders", "x")),
                moved(order(1, "a"), ("orders", "y")),
            ],
            relation: relation(None, "main", "orders"),
            expected_index: Some(0),
        },
        NewestMoveTestCase {
            description: "unrelated relation",
            events: vec![moved(order(1, "a"), ("orders", "x"))],
            relation: relation(None, "main", "customers"),
            expected_index: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            newest_move_event(&test_case.events, &test_case.relation),
            test_case.expected_index,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_column_renames_when_projecting_newest_mention_then_either_column_matches() {
    let test_cases = [
        NewestColumnTestCase {
            description: "destination column of a later rename matches case-insensitively",
            events: vec![
                renamed(order(1, "a"), ("amount", "total")),
                renamed(order(2, "b"), ("TOTAL", "net")),
            ],
            columns: ("x", "Total"),
            expected_index: Some(1),
        },
        NewestColumnTestCase {
            description: "no rename names either column",
            events: vec![renamed(order(1, "a"), ("amount", "total"))],
            columns: ("x", "y"),
            expected_index: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            newest_column_event(
                &test_case.events,
                &relation(None, "main", "orders"),
                test_case.columns
            ),
            test_case.expected_index,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_moves_and_facts_when_projecting_histories_then_earliest_fact_of_each_step_is_kept() {
    let test_cases = [
        HistoryTestCase {
            description: "moves sort by time and keep the earliest fact per step",
            moves: vec![order(3, "m2"), order(1, "m1"), order(1, "m0")],
            facts: vec![
                fact(order(2, "f3"), "m1", OldNameStep::Required),
                fact(order(2, "f2"), "m1", OldNameStep::Required),
                fact(order(1, "f9"), "m1", OldNameStep::ViewDropped),
                fact(order(1, "f1"), "m2", OldNameStep::Required),
                fact(order(1, "f4"), "m2", OldNameStep::OriginArchived),
                fact(order(1, "f5"), "m2", OldNameStep::ViewCreated),
                fact(order(1, "f6"), "m0", OldNameStep::ViewCreated),
            ],
            expected_histories: vec![
                OldNameHistoryIndexes {
                    moved: 1,
                    required: 1,
                    archived: None,
                    created: None,
                    dropped: Some(2),
                },
                OldNameHistoryIndexes {
                    moved: 0,
                    required: 3,
                    archived: Some(4),
                    created: Some(5),
                    dropped: None,
                },
            ],
        },
        HistoryTestCase {
            description: "no moves",
            moves: vec![],
            facts: vec![fact(order(1, "f1"), "m1", OldNameStep::Required)],
            expected_histories: vec![],
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            old_name_histories(&test_case.moves, &test_case.facts),
            test_case.expected_histories,
            "{}",
            test_case.description
        );
    }
}
