use crate::records::models::{OutputStream, RecallValue};
use crate::writer::models::SetupOutcome;
use crate::writer::tests::helpers::recorded_session;
#[cfg(unix)]
use crate::writer::tests::helpers::unwritable_session;
#[cfg(unix)]
use crate::writer::tests::test_types::UnwritableTestCase;
use crate::writer::tests::test_types::{RecordedSession, SessionTestCase};

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
