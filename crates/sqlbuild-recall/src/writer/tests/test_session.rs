use std::time::Duration;

use crate::records::models::{InvocationContext, OutputStream, RecallValue, RowEnvelope};
use crate::store::main::open_sqlite_store::open_sqlite_store;
use crate::store::main::query_store::query_store;
use crate::store::main::read_output_transcript::read_output_transcript;
use crate::store::models::OpenMode;
use crate::writer::main::start_recall_session::start_recall_session;
use crate::writer::models::{DeliveryStream, SessionConfig, SetupOutcome};

fn config(path: std::path::PathBuf, invocation_id: &str) -> SessionConfig {
    SessionConfig {
        store_path: path,
        envelope: RowEnvelope {
            invocation_id: invocation_id.to_owned(),
            invocation_started_at: "2026-10-19T00:00:00.000000Z".to_owned(),
            producer_version: "test".to_owned(),
        },
        context: InvocationContext {
            command: Some("build".to_owned()),
            pid: Some(42),
            ..InvocationContext::default()
        },
        retention_days: 30,
        shutdown_timeout: Duration::from_secs(5),
        diagnostics_min_severity: "info".to_owned(),
        heartbeat_interval: Duration::from_secs(30),
        setup_budget: Duration::from_secs(2),
        maintenance: true,
        maintenance_owner: "test:42".to_owned(),
    }
}

#[test]
fn given_a_session_when_closed_then_every_record_and_the_delivery_rows_are_written() {
    let directory = tempfile::tempdir().expect("temporary directory");
    let path = directory.path().join("logs/recall.sqlite3");
    let session = start_recall_session(config(path.clone(), "inv-1"));
    assert_eq!(
        session.wait_for_setup(Duration::from_secs(10)),
        Some(SetupOutcome::Ready)
    );
    let large: Vec<u8> = (0..200_000_u32).map(|value| (value % 251) as u8).collect();
    session.append_output(OutputStream::Stdout, b"start\n");
    session.append_output(OutputStream::Stderr, b"\xff\x00warn\n");
    session.append_output(OutputStream::Stdout, &large);
    session
        .publish_event(
            r#"{"event_id":"e1","event_type":"invocation_completed","schema_version":2,
            "producer":"sqlbuild","producer_version":"1","occurred_at":"2026-10-19T00:00:01.000000Z",
            "invocation_id":"inv-1","invocation_sequence":1,"payload":{"command":"build","exit_code":0,"duration_ms":3.0}}"#,
        )
        .expect("event");
    session
        .publish_diagnostic(r#"{"occurred_at":"2026-10-19T00:00:00.500000Z","severity":"debug","logger":"l","source":"python","message":"hidden"}"#)
        .expect("debug diagnostic");
    session
        .publish_diagnostic(r#"{"occurred_at":"2026-10-19T00:00:00.500000Z","severity":"warning","logger":"l","source":"python","message":"kept"}"#)
        .expect("warning diagnostic");
    session.publish_sql("select 1", Some("s1"), None);
    session.publish_sql("select 1", Some("s2"), None);
    let summary = session.close();
    assert_eq!(summary.degraded_reason, None);
    let total = summary.total();
    assert_eq!((total.dropped, total.failed), (0, 0));
    let output = summary
        .streams
        .iter()
        .find(|(stream, _)| *stream == DeliveryStream::Output)
        .expect("output counts")
        .1;
    assert_eq!(output.delivered, output.accepted);
    let store = open_sqlite_store(&path, OpenMode::ReadOnly).expect("read store");
    let transcript = read_output_transcript(&store, "inv-1", None).expect("transcript");
    let expected: Vec<u8> = [b"start\n".as_slice(), b"\xff\x00warn\n", &large].concat();
    assert_eq!(transcript.data, expected);
    assert!(transcript.complete, "{transcript:?}");
    let stdout =
        read_output_transcript(&store, "inv-1", Some(OutputStream::Stdout)).expect("stdout");
    assert_eq!(stdout.data, [b"start\n".as_slice(), &large].concat());
    let facts = query_store(
        &store,
        "SELECT (SELECT status FROM invocations), (SELECT COUNT(*) FROM recall_diagnostics), \
         (SELECT COUNT(*) FROM recall_artifacts), (SELECT COUNT(*) FROM recall_heartbeats), \
         (SELECT COUNT(*) FROM recall_delivery), (SELECT command FROM recall_invocations)",
        None,
    )
    .expect("facts");
    assert_eq!(
        facts.rows,
        vec![vec![
            RecallValue::Text("completed".to_owned()),
            RecallValue::Integer(1),
            RecallValue::Integer(1),
            RecallValue::Integer(1),
            RecallValue::Integer(5),
            RecallValue::Text("build".to_owned()),
        ]]
    );
}

#[cfg(unix)]
#[test]
fn given_an_unwritable_store_when_started_then_setup_reports_permission_and_close_is_quick() {
    use std::os::unix::fs::PermissionsExt;
    let directory = tempfile::tempdir().expect("temporary directory");
    std::fs::set_permissions(directory.path(), std::fs::Permissions::from_mode(0o555))
        .expect("chmod");
    let session = start_recall_session(config(
        directory.path().join("logs/recall.sqlite3"),
        "inv-2",
    ));
    let setup = session.wait_for_setup(Duration::from_secs(10));
    session.append_output(OutputStream::Stdout, b"still printed\n");
    let summary = session.close();
    std::fs::set_permissions(directory.path(), std::fs::Permissions::from_mode(0o755))
        .expect("restore");
    assert!(
        matches!(setup, Some(SetupOutcome::PermissionDenied { .. })),
        "{setup:?}"
    );
    assert!(summary.degraded_reason.is_some());
}
