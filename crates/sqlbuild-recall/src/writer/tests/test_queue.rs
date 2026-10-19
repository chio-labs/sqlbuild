use crate::records::models::{OutputStream, RecallValue};
use crate::writer::models::{DeliveryStream, Priority};
use crate::writer::tests::helpers::{capped, chunk_facts, chunked, output_drops, pushed};
use crate::writer::tests::test_types::{
    CaptureLimitTestCase, ChunkingTestCase, DisplacementTestCase, OutputDropTestCase,
};

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

#[test]
fn given_a_full_queue_when_output_is_dropped_then_each_drop_is_counted_once() {
    let test_cases = [OutputDropTestCase {
        description: "two chunks dropped by a full queue are counted once and reported once",
        capacity: 1,
        chunks: 4,
        expected_drops: (
            2,
            vec![Some(RecallValue::Integer(0)), Some(RecallValue::Integer(2))],
        ),
    }];

    for test_case in test_cases {
        assert_eq!(
            output_drops(test_case.capacity, test_case.chunks),
            test_case.expected_drops,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_output_past_the_limit_when_closed_then_head_and_tail_are_exact_around_one_gap() {
    let test_cases = [
        CaptureLimitTestCase {
            description: "output within the first half is one chunk",
            limit: Some(8),
            writes: vec![(OutputStream::Stdout, b"01"), (OutputStream::Stdout, b"23")],
            expected_rows: vec![chunk_facts((0, "stdout", 0), b"0123", None)],
        },
        CaptureLimitTestCase {
            description: "output within the limit is kept whole around an empty gap",
            limit: Some(8),
            writes: vec![
                (OutputStream::Stdout, b"0123"),
                (OutputStream::Stdout, b"45"),
            ],
            expected_rows: vec![
                chunk_facts((0, "stdout", 0), b"0123", None),
                chunk_facts((1, "stdout", 4), b"", Some((0, 1))),
                chunk_facts((2, "stdout", 4), b"45", None),
            ],
        },
        CaptureLimitTestCase {
            description: "the first and last halves are kept around a gap counting the middle",
            limit: Some(8),
            writes: vec![(OutputStream::Stdout, b"0123456789")],
            expected_rows: vec![
                chunk_facts((0, "stdout", 0), b"0123", None),
                chunk_facts((1, "stdout", 4), b"", Some((2, 1))),
                chunk_facts((2, "stdout", 6), b"6789", None),
            ],
        },
        CaptureLimitTestCase {
            description: "interleaved stderr keeps its place around the kept stdout tail",
            limit: Some(8),
            writes: vec![
                (OutputStream::Stdout, b"0123"),
                (OutputStream::Stdout, b"ab"),
                (OutputStream::Stderr, b"E1"),
                (OutputStream::Stdout, b"cdef"),
                (OutputStream::Stdout, b"gh"),
                (OutputStream::Stderr, b"E2"),
            ],
            expected_rows: vec![
                chunk_facts((0, "stdout", 0), b"0123", None),
                chunk_facts((1, "stdout", 4), b"", Some((4, 2))),
                chunk_facts((3, "stderr", 0), b"E1", None),
                chunk_facts((4, "stdout", 8), b"efgh", None),
                chunk_facts((5, "stderr", 2), b"E2", None),
            ],
        },
        CaptureLimitTestCase {
            description: "no limit records everything",
            limit: None,
            writes: vec![(OutputStream::Stdout, b"0123456789")],
            expected_rows: vec![chunk_facts((0, "stdout", 0), b"0123456789", None)],
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            capped(test_case.limit, &test_case.writes),
            test_case.expected_rows,
            "{}",
            test_case.description
        );
    }
}
