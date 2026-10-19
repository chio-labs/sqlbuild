use std::path::PathBuf;
use std::time::{Duration, SystemTime};

use crate::records::main::invocation_row::invocation_row;
use crate::records::models::{InvocationContext, OutputStream, RecallValue, RowEnvelope};
use crate::store::main::open_sqlite_store::open_sqlite_store;
use crate::store::main::query_store::query_store;
use crate::store::main::read_output_transcript::read_output_transcript;
use crate::store::models::OpenMode;
use crate::writer::_helpers::queue::WriterState;
use crate::writer::main::start_recall_session::start_recall_session;
use crate::writer::models::{DeliveryStream, Priority, SessionConfig, SetupOutcome};
use crate::writer::tests::test_types::RecordedSession;

/// The envelope of invocation `invocation_id`.
pub(crate) fn envelope(invocation_id: &str) -> RowEnvelope {
    RowEnvelope {
        invocation_id: invocation_id.to_owned(),
        invocation_started_at: "2026-10-19T00:00:00.000000Z".to_owned(),
        producer_version: "test".to_owned(),
    }
}

/// Dropped counts per stream and the streams taken after pushing `pushes` into `capacity`.
pub(crate) fn pushed(
    capacity: usize,
    pushes: &[(DeliveryStream, Priority)],
) -> (Vec<(DeliveryStream, u64)>, Vec<DeliveryStream>) {
    let mut state = WriterState::with_capacity(envelope("inv"), (capacity, usize::MAX));
    for (stream, priority) in pushes {
        state.push(
            vec![invocation_row(
                &envelope("inv"),
                &InvocationContext::default(),
            )],
            *stream,
            *priority,
        );
    }
    let mut streams: Vec<DeliveryStream> = pushes.iter().map(|(stream, _)| *stream).collect();
    streams.dedup();
    let dropped: Vec<(DeliveryStream, u64)> = streams
        .iter()
        .map(|stream| (*stream, state.counts[stream.index()].dropped))
        .collect();
    let taken: Vec<DeliveryStream> = state
        .take_batch(usize::MAX)
        .iter()
        .map(|record| record.stream)
        .collect();
    (dropped, taken)
}

/// `(sequence, stream, byte_offset)` of each output chunk after `writes` and a flush.
pub(crate) fn chunked(writes: &[(OutputStream, Vec<u8>)]) -> Vec<[Option<RecallValue>; 3]> {
    let mut state = WriterState::new(envelope("inv"));
    for (stream, data) in writes {
        state.append_output(*stream, data, SystemTime::now());
    }
    state.flush_output();
    state
        .take_batch(usize::MAX)
        .into_iter()
        .flat_map(|record| record.rows)
        .map(|row| ["sequence", "stream", "byte_offset"].map(|name| row.value(name).cloned()))
        .collect()
}

/// A session configuration writing invocation `invocation_id` to `path`.
pub(crate) fn config(path: PathBuf, invocation_id: &str) -> SessionConfig {
    SessionConfig {
        store_path: path,
        envelope: envelope(invocation_id),
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

/// Run a session that writes `output`, one completed event, two diagnostics and one SQL twice.
pub(crate) fn recorded_session(output: &[(OutputStream, Vec<u8>)]) -> RecordedSession {
    let directory = tempfile::tempdir().expect("a temporary directory can be created");
    let path = directory.path().join("logs/recall.sqlite3");
    let session = start_recall_session(config(path.clone(), "inv-1"));
    let setup = session.wait_for_setup(Duration::from_secs(10));
    for (stream, data) in output {
        session.append_output(*stream, data);
    }
    session
        .publish_event(
            r#"{"event_id":"e1","event_type":"invocation_completed","schema_version":2,
            "producer":"sqlbuild","producer_version":"1","occurred_at":"2026-10-19T00:00:01.000000Z",
            "invocation_id":"inv-1","invocation_sequence":1,"payload":{"command":"build","exit_code":0,"duration_ms":3.0}}"#,
        )
        .expect("the event is valid");
    for severity in ["debug", "warning"] {
        session
            .publish_diagnostic(&format!(
                r#"{{"occurred_at":"2026-10-19T00:00:00.500000Z","severity":"{severity}","logger":"l","source":"python","message":"m"}}"#
            ))
            .expect("the diagnostic is valid");
    }
    session.publish_sql("select 1", Some("s1"), None);
    session.publish_sql("select 1", Some("s2"), None);
    let summary = session.close();
    let total = summary.total();
    let output_fully_delivered: bool = summary
        .streams
        .iter()
        .find(|(stream, _)| *stream == DeliveryStream::Output)
        .is_some_and(|(_, counts)| counts.delivered == counts.accepted);
    let store = open_sqlite_store(&path, OpenMode::ReadOnly).expect("the store opens");
    let transcript =
        read_output_transcript(&store, "inv-1", None).expect("the transcript can be read");
    let stdout = read_output_transcript(&store, "inv-1", Some(OutputStream::Stdout))
        .expect("the transcript can be read");
    let facts = query_store(
        &store,
        "SELECT (SELECT status FROM invocations), (SELECT COUNT(*) FROM recall_diagnostics), \
         (SELECT COUNT(*) FROM recall_artifacts), (SELECT COUNT(*) FROM recall_heartbeats), \
         (SELECT COUNT(*) FROM recall_delivery), (SELECT command FROM recall_invocations)",
        None,
    )
    .expect("the query is valid");
    RecordedSession {
        setup,
        lost: (total.dropped, total.failed),
        output_fully_delivered,
        transcript: (transcript.data, transcript.complete),
        stdout: stdout.data,
        facts: facts.rows,
    }
}

/// Whether a store under a read-only directory reports permission at setup and degrades.
#[cfg(unix)]
pub(crate) fn unwritable_session() -> (bool, bool) {
    use std::os::unix::fs::PermissionsExt;
    let directory = tempfile::tempdir().expect("a temporary directory can be created");
    std::fs::set_permissions(directory.path(), std::fs::Permissions::from_mode(0o555))
        .expect("test directory permissions can change");
    let session = start_recall_session(config(
        directory.path().join("logs/recall.sqlite3"),
        "inv-2",
    ));
    let setup = session.wait_for_setup(Duration::from_secs(10));
    session.append_output(OutputStream::Stdout, b"still printed\n");
    let summary = session.close();
    std::fs::set_permissions(directory.path(), std::fs::Permissions::from_mode(0o755))
        .expect("test directory permissions can change");
    (
        matches!(setup, Some(SetupOutcome::PermissionDenied { .. })),
        summary.degraded_reason.is_some(),
    )
}
