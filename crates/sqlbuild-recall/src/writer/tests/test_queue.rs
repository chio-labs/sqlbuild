use std::time::SystemTime;

use crate::records::main::invocation_row::invocation_row;
use crate::records::models::{InvocationContext, OutputStream, RowEnvelope};
use crate::writer::_helpers::queue::WriterState;
use crate::writer::models::{DeliveryStream, Priority};

fn envelope() -> RowEnvelope {
    RowEnvelope {
        invocation_id: "inv".to_owned(),
        invocation_started_at: "2026-10-19T00:00:00.000000Z".to_owned(),
        producer_version: "test".to_owned(),
    }
}

#[test]
fn given_a_full_queue_when_higher_priority_arrives_then_the_oldest_lowest_is_displaced() {
    let mut state = WriterState::with_capacity(envelope(), (2, usize::MAX));
    let row = || vec![invocation_row(&envelope(), &InvocationContext::default())];
    state.push(
        row(),
        DeliveryStream::Diagnostics,
        Priority::DebugDiagnostic,
    );
    state.push(row(), DeliveryStream::Artifacts, Priority::Artifact);
    state.push(row(), DeliveryStream::Events, Priority::FailedTerminal);
    state.push(
        row(),
        DeliveryStream::Diagnostics,
        Priority::DebugDiagnostic,
    );
    assert_eq!(state.counts[DeliveryStream::Diagnostics.index()].dropped, 2);
    assert_eq!(state.counts[DeliveryStream::Artifacts.index()].dropped, 0);
    let batch = state.take_batch(10);
    let streams: Vec<DeliveryStream> = batch.iter().map(|record| record.stream).collect();
    assert_eq!(
        streams,
        vec![DeliveryStream::Events, DeliveryStream::Artifacts]
    );
}

#[test]
fn given_interleaved_and_large_writes_when_chunked_then_sequences_and_offsets_are_exact() {
    let mut state = WriterState::new(envelope());
    let big = vec![b'a'; 64 * 1024 + 10];
    state.append_output(OutputStream::Stdout, b"one ", SystemTime::now());
    state.append_output(OutputStream::Stdout, b"two\n", SystemTime::now());
    state.append_output(OutputStream::Stderr, b"err\n", SystemTime::now());
    state.append_output(OutputStream::Stdout, &big, SystemTime::now());
    state.flush_output();
    let rows: Vec<_> = state
        .take_batch(100)
        .into_iter()
        .flat_map(|record| record.rows)
        .collect();
    let summary: Vec<(String, String, String)> = rows
        .iter()
        .map(|row| {
            let text = |name: &str| format!("{:?}", row.value(name).expect(name));
            (text("sequence"), text("stream"), text("byte_offset"))
        })
        .collect();
    assert_eq!(
        summary,
        vec![
            (
                "Integer(0)".into(),
                "Text(\"stdout\")".into(),
                "Integer(0)".into()
            ),
            (
                "Integer(1)".into(),
                "Text(\"stderr\")".into(),
                "Integer(0)".into()
            ),
            (
                "Integer(2)".into(),
                "Text(\"stdout\")".into(),
                "Integer(8)".into()
            ),
            (
                "Integer(3)".into(),
                "Text(\"stdout\")".into(),
                "Integer(65544)".into()
            ),
        ]
    );
}
