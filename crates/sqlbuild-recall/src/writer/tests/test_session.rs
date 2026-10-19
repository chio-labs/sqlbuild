use std::time::Duration;

use crate::records::models::{OutputStream, RecallValue};
use crate::writer::models::SetupOutcome;

#[cfg(unix)]
use crate::writer::tests::helpers::unwritable_session;
use crate::writer::tests::helpers::{
    artifact_counts, close_under_held_lock, event_counts, output_stored_while_running,
    recorded_session, session_on_corrupt_store,
};
#[cfg(unix)]
use crate::writer::tests::test_types::UnwritableTestCase;
use crate::writer::tests::test_types::{
    ArtifactSizeTestCase, CorruptStoreTestCase, EventBuildTestCase, HeldLockTestCase,
    RecordedSession, SessionTestCase, StoredWhileRunningTestCase,
};

const CLOSE_SLACK_SECONDS: f64 = 0.3;

#[test]
fn given_a_session_when_closed_then_every_record_and_the_delivery_rows_are_written() {
    let large: Vec<u8> = (0..200_000_u32)
        .map(|value| u8::try_from(value % 251).unwrap_or_default())
        .collect();
    let test_cases = [SessionTestCase {
        description: "binary output, events, filtered diagnostics and deduplicated SQL land",
        output: vec![
            (OutputStream::Stdout, b"start\n".to_vec()),
            (OutputStream::Stderr, b"\xff\x00warn\n".to_vec()),
            (OutputStream::Stdout, large.clone()),
        ],
        expected_session: RecordedSession {
            setup: Some(SetupOutcome::Ready),
            lost: (0, 0),
            output_fully_delivered: true,
            transcript: (
                [b"start\n".as_slice(), b"\xff\x00warn\n", &large].concat(),
                true,
            ),
            stdout: [b"start\n".as_slice(), &large].concat(),
            facts: vec![vec![
                RecallValue::Text("completed".to_owned()),
                RecallValue::Integer(1),
                RecallValue::Integer(1),
                RecallValue::Integer(5),
                RecallValue::Text("build".to_owned()),
            ]],
        },
    }];

    for test_case in test_cases {
        assert_eq!(
            recorded_session(&test_case.output),
            test_case.expected_session,
            "{}",
            test_case.description
        );
    }
}

#[cfg(unix)]
#[test]
fn given_an_unwritable_store_when_started_then_setup_reports_permission_and_close_is_quick() {
    let test_cases = [UnwritableTestCase {
        description: "permission is reported at setup and the summary is degraded",
        expected_permission_and_degraded: (true, true),
    }];

    for test_case in test_cases {
        assert_eq!(
            unwritable_session(),
            test_case.expected_permission_and_degraded,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_a_held_write_lock_when_closed_then_the_shutdown_budget_caps_the_delay() {
    let test_cases = [HeldLockTestCase {
        description: "a locked store costs at most the shutdown budget at exit",
        shutdown_ms: 700,
        expected_degraded: true,
    }];

    for test_case in test_cases {
        let (elapsed, degraded) =
            close_under_held_lock(Duration::from_millis(test_case.shutdown_ms));
        let budget: f64 = Duration::from_millis(test_case.shutdown_ms).as_secs_f64();
        assert!(
            elapsed <= budget + CLOSE_SLACK_SECONDS,
            "{}: {elapsed:.3}s",
            test_case.description
        );
        assert_eq!(
            degraded, test_case.expected_degraded,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_a_file_that_is_not_a_database_when_started_then_it_is_moved_aside_once() {
    let test_cases = [CorruptStoreTestCase {
        description: "the corrupt file is kept aside and a fresh store records the run",
        expected_notices: 1,
        expected_moved: true,
        expected_rows: vec![vec![RecallValue::Text("unknown".to_owned())]],
    }];

    for test_case in test_cases {
        assert_eq!(
            session_on_corrupt_store(),
            (
                test_case.expected_notices,
                test_case.expected_moved,
                test_case.expected_rows
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_sql_of_different_sizes_when_published_then_oversized_sql_is_dropped_unhashed() {
    let test_cases = [
        ArtifactSizeTestCase {
            description: "ordinary SQL is delivered with its reference",
            length: 64,
            times: 1,
            expected_counts: (1, 1, 0, vec![vec![RecallValue::Integer(1)]]),
        },
        ArtifactSizeTestCase {
            description: "SQL seen twice is stored once and both records count as delivered",
            length: 64,
            times: 2,
            expected_counts: (2, 2, 0, vec![vec![RecallValue::Integer(1)]]),
        },
        ArtifactSizeTestCase {
            description: "SQL above the artifact limit is counted as dropped",
            length: 4 * 1024 * 1024 + 1,
            times: 1,
            expected_counts: (1, 0, 1, vec![vec![RecallValue::Integer(0)]]),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            artifact_counts(test_case.length, test_case.times),
            test_case.expected_counts,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_events_when_built_on_the_delivery_thread_then_unbuildable_ones_count_as_failed() {
    let valid: &str = r#"{"event_id":"e1","event_type":"invocation_started","schema_version":2,
        "producer":"sqlbuild","producer_version":"1","occurred_at":"2026-10-19T00:00:00.000000Z",
        "invocation_id":"events","invocation_sequence":1,"external_context":{},"payload":{}}"#;
    let test_cases = [
        EventBuildTestCase {
            description: "a complete event is delivered",
            events: vec![valid],
            expected_counts: (1, 1, 0),
        },
        EventBuildTestCase {
            description: "an event without an ID is accepted, then counted as failed",
            events: vec![valid, r#"{"event_type":"invocation_started"}"#],
            expected_counts: (2, 1, 1),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            event_counts(&test_case.events),
            test_case.expected_counts,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_heartbeats_due_faster_than_batches_fill_when_running_then_queued_records_are_still_written()
 {
    let test_cases = [StoredWhileRunningTestCase {
        description: "a 50 ms heartbeat still lets queued output reach the store",
        heartbeat: Duration::from_millis(50),
        wait: Duration::from_millis(1_500),
        expected_rows: vec![vec![RecallValue::Integer(1)]],
    }];

    for test_case in test_cases {
        assert_eq!(
            output_stored_while_running(test_case.heartbeat, test_case.wait),
            test_case.expected_rows,
            "{}",
            test_case.description
        );
    }
}
