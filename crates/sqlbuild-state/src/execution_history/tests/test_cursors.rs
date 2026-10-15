use crate::execution_history::main::decoded_run_cursor::decoded_run_cursor;
use crate::execution_history::main::event_cursor_position::event_cursor_position;
use crate::execution_history::main::run_cursor::run_cursor;
use crate::execution_history::models::Dialect;
use crate::execution_history::tests::helpers::run_row;
use crate::execution_history::tests::test_types::{
    CursorRejectionTestCase, EventCursorTestCase, RunCursorTestCase,
};

#[test]
fn given_runs_when_encoding_cursors_then_python_base64_json_round_trips() {
    let test_cases = [
        RunCursorTestCase {
            description: "SQLite cursors carry microsecond text",
            dialect: Dialect::Sqlite,
            run: run_row("r1", 1, 1),
            expected_cursor: "sqlite-run:WyJucyIsIjIwMjYtMDEtMDFUMDA6MDA6MDAuMDAwMDAwKzAwOjAwIiwicjEiXQ==",
            expected_created_at: "2026-01-01T00:00:00.000000+00:00",
        },
        RunCursorTestCase {
            description: "PostgreSQL cursors carry isoformat text and escape non-ASCII",
            dialect: Dialect::Postgres,
            run: run_row("r\u{e9}", 1, 1),
            expected_cursor: "postgres-run:WyJucyIsIjIwMjYtMDEtMDFUMDA6MDA6MDArMDA6MDAiLCJyXHUwMGU5Il0=",
            expected_created_at: "2026-01-01T00:00:00+00:00",
        },
    ];

    for test_case in test_cases {
        let cursor = run_cursor(test_case.dialect, "ns", &test_case.run);
        let decoded = cursor
            .clone()
            .and_then(|cursor| decoded_run_cursor(test_case.dialect, &cursor, "ns"))
            .map(|decoded| (decoded.created_at_text, decoded.run_id));
        assert_eq!(
            (cursor, decoded),
            (
                Ok(test_case.expected_cursor.to_owned()),
                Ok((
                    test_case.expected_created_at.to_owned(),
                    test_case.run.run_id.clone()
                ))
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_foreign_run_cursors_when_decoding_then_they_are_malformed() {
    let test_cases = [
        CursorRejectionTestCase {
            description: "other backend prefix",
            dialect: Dialect::Postgres,
            cursor: "sqlite-run:WyJucyIsIjIwMjYtMDEtMDFUMDA6MDA6MDAuMDAwMDAwKzAwOjAwIiwicjEiXQ==",
            expected_message: "run cursor is malformed or belongs to another backend",
        },
        CursorRejectionTestCase {
            description: "bad base64",
            dialect: Dialect::Sqlite,
            cursor: "sqlite-run:@@@@",
            expected_message: "run cursor is malformed or belongs to another backend",
        },
        CursorRejectionTestCase {
            description: "another namespace",
            dialect: Dialect::Sqlite,
            cursor: "sqlite-run:WyJvdGhlciIsIngiLCJyIl0=",
            expected_message: "run cursor is malformed or belongs to another backend",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            decoded_run_cursor(test_case.dialect, test_case.cursor, "ns")
                .map_err(|error| error.message),
            Err(test_case.expected_message.to_owned()),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_event_cursors_when_reading_positions_then_python_rules_apply() {
    let test_cases = [
        EventCursorTestCase {
            description: "no cursor starts at zero",
            cursor: None,
            expected_position: Ok(0),
        },
        EventCursorTestCase {
            description: "own cursor",
            cursor: Some("sqlite-event:ns:7"),
            expected_position: Ok(7),
        },
        EventCursorTestCase {
            description: "too few parts",
            cursor: Some("sqlite-event"),
            expected_position: Err("event cursor is malformed or belongs to another backend"),
        },
        EventCursorTestCase {
            description: "non-numeric position",
            cursor: Some("sqlite-event:ns:x"),
            expected_position: Err("event cursor is malformed or belongs to another backend"),
        },
        EventCursorTestCase {
            description: "another namespace",
            cursor: Some("sqlite-event:other:7"),
            expected_position: Err("event cursor is not valid for this storage"),
        },
        EventCursorTestCase {
            description: "position zero",
            cursor: Some("sqlite-event:ns:0"),
            expected_position: Err("event cursor is not valid for this storage"),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            event_cursor_position(Dialect::Sqlite, test_case.cursor, "ns")
                .map_err(|error| error.message),
            test_case.expected_position.map_err(str::to_owned),
            "{}",
            test_case.description
        );
    }
}
