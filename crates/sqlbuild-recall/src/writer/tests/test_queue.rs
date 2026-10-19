use crate::records::models::{OutputStream, RecallValue};
use crate::writer::models::{DeliveryStream, Priority};
use crate::writer::tests::helpers::{chunked, pushed};
use crate::writer::tests::test_types::{ChunkingTestCase, DisplacementTestCase};

#[test]
fn given_a_full_queue_when_higher_priority_arrives_then_the_oldest_lowest_is_displaced() {
    let test_cases = [
        DisplacementTestCase {
            description: "debug diagnostics give way first, artifacts survive",
            capacity: 2,
            pushes: &[
                (DeliveryStream::Diagnostics, Priority::DebugDiagnostic),
                (DeliveryStream::Artifacts, Priority::Artifact),
                (DeliveryStream::Events, Priority::FailedTerminal),
                (DeliveryStream::Diagnostics, Priority::DebugDiagnostic),
            ],
            expected_dropped: vec![
                (DeliveryStream::Diagnostics, 2),
                (DeliveryStream::Artifacts, 0),
                (DeliveryStream::Events, 0),
                (DeliveryStream::Diagnostics, 2),
            ],
            expected_taken: vec![DeliveryStream::Events, DeliveryStream::Artifacts],
        },
        DisplacementTestCase {
            description: "a queue with room keeps everything in priority order",
            capacity: 4,
            pushes: &[
                (DeliveryStream::Diagnostics, Priority::DebugDiagnostic),
                (DeliveryStream::Events, Priority::FailedTerminal),
            ],
            expected_dropped: vec![
                (DeliveryStream::Diagnostics, 0),
                (DeliveryStream::Events, 0),
            ],
            expected_taken: vec![DeliveryStream::Events, DeliveryStream::Diagnostics],
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            pushed(test_case.capacity, test_case.pushes),
            (test_case.expected_dropped, test_case.expected_taken),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_interleaved_and_large_writes_when_chunked_then_sequences_and_offsets_are_exact() {
    let chunk = |sequence: i64, stream: &str, offset: i64| {
        [
            Some(RecallValue::Integer(sequence)),
            Some(RecallValue::Text(stream.to_owned())),
            Some(RecallValue::Integer(offset)),
        ]
    };
    let test_cases = [
        ChunkingTestCase {
            description: "adjacent writes coalesce, stream switches and 64KiB split chunks",
            writes: vec![
                (OutputStream::Stdout, b"one ".to_vec()),
                (OutputStream::Stdout, b"two\n".to_vec()),
                (OutputStream::Stderr, b"err\n".to_vec()),
                (OutputStream::Stdout, vec![b'a'; 64 * 1024 + 10]),
            ],
            expected_chunks: vec![
                chunk(0, "stdout", 0),
                chunk(1, "stderr", 0),
                chunk(2, "stdout", 8),
                chunk(3, "stdout", 65_544),
            ],
        },
        ChunkingTestCase {
            description: "one small write is one chunk",
            writes: vec![(OutputStream::Stderr, b"only\n".to_vec())],
            expected_chunks: vec![chunk(0, "stderr", 0)],
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            chunked(&test_case.writes),
            test_case.expected_chunks,
            "{}",
            test_case.description
        );
    }
}
