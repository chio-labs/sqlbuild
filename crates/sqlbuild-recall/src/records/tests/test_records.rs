use std::time::{Duration, UNIX_EPOCH};

use crate::records::_helpers::ids::content_sha256;
use crate::records::_helpers::ids::diagnostic_record_id;
use crate::records::_helpers::ids::output_record_id;
use crate::records::main::diagnostic_input_from_json::diagnostic_input_from_json;
use crate::records::main::event_row::event_row;
use crate::records::main::format_timestamp::format_timestamp;
use crate::records::main::output_row::output_row;
use crate::records::main::parse_timestamp::parse_timestamp;
use crate::records::models::{OutputChunk, OutputStream, RecallValue, RowEnvelope};

fn envelope() -> RowEnvelope {
    RowEnvelope {
        invocation_id: "inv1".to_owned(),
        invocation_started_at: "2026-10-19T00:00:00.000000Z".to_owned(),
        producer_version: "0.0.0".to_owned(),
    }
}

#[test]
fn given_sequences_when_ids_are_built_then_they_follow_the_record_id_scheme() {
    assert_eq!(output_record_id("abc", 7), "abc:command-output:7");
    assert_eq!(diagnostic_record_id("abc", 0), "abc:diagnostic:0");
}

#[test]
fn given_times_when_formatted_and_parsed_then_they_round_trip() {
    let cases = [
        (0_u64, "1970-01-01T00:00:00.000000Z"),
        (951_782_400_123_456, "2000-02-29T00:00:00.123456Z"),
        (1_792_281_600_000_001, "2026-10-18T00:00:00.000001Z"),
    ];
    for (micros, expected) in cases {
        let time = UNIX_EPOCH + Duration::from_micros(micros);
        assert_eq!(format_timestamp(time), expected);
        assert_eq!(parse_timestamp(expected), Some(time));
    }
    assert_eq!(
        parse_timestamp("2026-10-18T00:00:00+00:00"),
        parse_timestamp("2026-10-18T00:00:00.000000Z")
    );
    assert_eq!(parse_timestamp("yesterday"), None);
}

#[test]
fn given_equal_and_different_content_when_hashed_then_only_content_matters() {
    let base = vec![
        ("a", RecallValue::Text("x".to_owned())),
        ("b", RecallValue::Integer(1)),
    ];
    let reordered = vec![
        ("b", RecallValue::Integer(1)),
        ("a", RecallValue::Text("x".to_owned())),
        ("ingested_at", RecallValue::Text("later".to_owned())),
    ];
    let changed = vec![
        ("a", RecallValue::Blob(b"x".to_vec())),
        ("b", RecallValue::Integer(1)),
    ];
    assert_eq!(content_sha256(&base), content_sha256(&reordered));
    assert_ne!(content_sha256(&base), content_sha256(&changed));
}

#[test]
fn given_a_chunk_when_rowed_then_bytes_and_offsets_are_kept() {
    let row = output_row(
        &envelope(),
        &OutputChunk {
            sequence: 3,
            stream: OutputStream::Stderr,
            occurred_at: "2026-10-19T00:00:01.000000Z".to_owned(),
            data: vec![0, 255, 10],
            byte_offset: 12,
            dropped_before: 1,
        },
    );
    assert_eq!(
        row.value("data"),
        Some(&RecallValue::Blob(vec![0, 255, 10]))
    );
    assert_eq!(row.value("byte_count"), Some(&RecallValue::Integer(3)));
    assert_eq!(
        row.value("record_id"),
        Some(&RecallValue::Text("inv1:command-output:3".to_owned()))
    );
    assert!(
        row.content_sha256()
            .is_some_and(|digest| digest.len() == 64)
    );
}

#[test]
fn given_lifecycle_json_when_rowed_then_dimensions_are_promoted() {
    let json = r#"{"event_id":"e1","event_type":"statement_failed","schema_version":2,
        "producer":"sqlbuild","producer_version":"1","occurred_at":"2026-10-19T00:00:02.000000Z",
        "invocation_id":"inv1","invocation_sequence":4,"statement_id":"s1",
        "payload":{"error_type":"ValueError","duration_ms":1.5,"sql_digest":"ab","purpose":"audit"}}"#;
    let row = event_row(&envelope(), json).expect("valid event");
    assert_eq!(
        row.value("event_kind"),
        Some(&RecallValue::Text("statement".to_owned()))
    );
    assert_eq!(
        row.value("severity"),
        Some(&RecallValue::Text("error".to_owned()))
    );
    assert_eq!(
        row.value("statement_id"),
        Some(&RecallValue::Text("s1".to_owned()))
    );
    assert_eq!(row.value("duration_ms"), Some(&RecallValue::Real(1.5)));
    assert_eq!(
        row.value("purpose"),
        Some(&RecallValue::Text("audit".to_owned()))
    );
    assert_eq!(
        row.value("invocation_sequence"),
        Some(&RecallValue::Integer(4))
    );
    assert!(event_row(&envelope(), "[]").is_err());
    assert!(event_row(&envelope(), r#"{"event_type":"x"}"#).is_err());
}

#[test]
fn given_diagnostic_json_when_parsed_then_correlations_are_kept() {
    let json = r#"{"occurred_at":"2026-10-19T00:00:00.000000Z","severity":"warning",
        "logger":"sqlbuild.x","source":"python","message":"careful","fields":{"k":1},
        "run_id":"r1"}"#;
    let diagnostic = diagnostic_input_from_json(json, 5).expect("valid diagnostic");
    assert_eq!(diagnostic.sequence, 5);
    assert_eq!(diagnostic.fields, r#"{"k":1}"#);
    assert_eq!(diagnostic.correlations.run_id.as_deref(), Some("r1"));
    assert!(diagnostic_input_from_json(r#"{"severity":"info"}"#, 0).is_err());
}
