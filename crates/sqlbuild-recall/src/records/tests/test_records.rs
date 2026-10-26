use std::time::{Duration, UNIX_EPOCH};

use crate::records::_helpers::ids::content_hash;
use crate::records::_helpers::ids::diagnostic_record_id;
use crate::records::_helpers::ids::output_record_id;
use crate::records::main::command_mode::command_mode;
use crate::records::main::diagnostic_input_from_json::diagnostic_input_from_json;
use crate::records::main::format_timestamp::format_timestamp;
use crate::records::main::invocation_origin::invocation_origin;
use crate::records::main::output_row::output_row;
use crate::records::main::parse_timestamp::parse_timestamp;
use crate::records::models::{OutputChunk, OutputStream, RecallValue};
use crate::records::tests::helpers::{envelope, event_row, present, row_columns, text};
use crate::records::tests::test_types::{
    CommandModeTestCase, ContentHashTestCase, DiagnosticTestCase, OriginTestCase,
    ParseTimestampTestCase, RecordIdTestCase, RejectedInputTestCase, RowColumnsTestCase,
    TimestampTestCase,
};

#[test]
fn given_sequences_when_ids_are_built_then_they_follow_the_record_id_scheme() {
    let test_cases = [
        RecordIdTestCase {
            description: "output chunks are keyed by invocation and sequence",
            record_id: output_record_id("abc", 7),
            expected_record_id: "abc:command-output:7",
        },
        RecordIdTestCase {
            description: "diagnostics are keyed by invocation and sequence",
            record_id: diagnostic_record_id("abc", 0),
            expected_record_id: "abc:diagnostic:0",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            test_case.record_id, test_case.expected_record_id,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_times_when_formatted_and_parsed_then_they_round_trip() {
    let test_cases = [
        TimestampTestCase {
            description: "the epoch",
            micros: 0,
            expected_text: "1970-01-01T00:00:00.000000Z",
        },
        TimestampTestCase {
            description: "a leap day with microseconds",
            micros: 951_782_400_123_456,
            expected_text: "2000-02-29T00:00:00.123456Z",
        },
        TimestampTestCase {
            description: "one microsecond past midnight",
            micros: 1_792_281_600_000_001,
            expected_text: "2026-10-18T00:00:00.000001Z",
        },
    ];

    for test_case in test_cases {
        let time = UNIX_EPOCH + Duration::from_micros(test_case.micros);
        assert_eq!(
            (
                format_timestamp(time),
                parse_timestamp(test_case.expected_text)
            ),
            (test_case.expected_text.to_owned(), Some(time)),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_timestamp_text_when_parsed_then_offsets_are_accepted_and_garbage_rejected() {
    let test_cases = [
        ParseTimestampTestCase {
            description: "a zero offset equals Z",
            text: "2026-10-18T00:00:00+00:00",
            expected_micros: Some(1_792_281_600_000_000),
        },
        ParseTimestampTestCase {
            description: "missing fractions are zero",
            text: "2026-10-18T00:00:00Z",
            expected_micros: Some(1_792_281_600_000_000),
        },
        ParseTimestampTestCase {
            description: "words are not timestamps",
            text: "yesterday",
            expected_micros: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            parse_timestamp(test_case.text),
            test_case
                .expected_micros
                .map(|micros| UNIX_EPOCH + Duration::from_micros(micros)),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_equal_and_different_content_when_hashed_then_only_content_matters() {
    let test_cases = [
        ContentHashTestCase {
            description: "column order and ingestion time do not matter",
            left: vec![("a", text("x")), ("b", RecallValue::Integer(1))],
            right: vec![
                ("b", RecallValue::Integer(1)),
                ("a", text("x")),
                ("ingested_at", text("later")),
            ],
            expected_equal: true,
        },
        ContentHashTestCase {
            description: "value types matter",
            left: vec![("a", text("x")), ("b", RecallValue::Integer(1))],
            right: vec![
                ("a", RecallValue::Blob(b"x".to_vec())),
                ("b", RecallValue::Integer(1)),
            ],
            expected_equal: false,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            content_hash(&test_case.left) == content_hash(&test_case.right),
            test_case.expected_equal,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_records_when_rowed_then_columns_are_promoted() {
    let lifecycle = r#"{"event_id":"e1","event_type":"statement_failed","schema_version":2,
        "producer":"sqlbuild","producer_version":"1","occurred_at":"2026-10-19T00:00:02.000000Z",
        "invocation_id":"inv1","invocation_sequence":4,"statement_id":"s1",
        "payload":{"error_type":"ValueError","duration_ms":1.5,"sql_digest":"ab","purpose":"audit"}}"#;
    let test_cases = [
        RowColumnsTestCase {
            description: "output chunks keep bytes, counts and record ids",
            row: output_row(
                &envelope(),
                &OutputChunk {
                    sequence: 3,
                    stream: OutputStream::Stderr,
                    occurred_at: "2026-10-19T00:00:01.000000Z".to_owned(),
                    data: vec![0, 255, 10],
                    byte_offset: 12,
                    dropped_before: 1,
                    omitted: None,
                },
            ),
            expected_columns: vec![
                ("data", RecallValue::Blob(vec![0, 255, 10])),
                ("byte_count", RecallValue::Integer(3)),
                ("byte_offset", RecallValue::Integer(12)),
                ("record_id", text("inv1:command-output:3")),
            ],
        },
        RowColumnsTestCase {
            description: "lifecycle events promote kind, severity and payload dimensions",
            row: event_row(&envelope(), lifecycle).expect("the fixture is a valid lifecycle event"),
            expected_columns: vec![
                ("event_kind", text("statement")),
                ("severity", text("error")),
                ("statement_id", text("s1")),
                ("duration_ms", RecallValue::Real(1.5)),
                ("purpose", text("audit")),
                ("invocation_sequence", RecallValue::Integer(4)),
            ],
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            row_columns(&test_case.row, &test_case.expected_columns),
            present(test_case.expected_columns),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_malformed_lifecycle_json_when_rowed_then_it_is_rejected() {
    let test_cases = [
        RejectedInputTestCase {
            description: "an array is not an event",
            json: "[]",
            expected_rejected: true,
        },
        RejectedInputTestCase {
            description: "an event needs its identity fields",
            json: r#"{"event_type":"x"}"#,
            expected_rejected: true,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            event_row(&envelope(), test_case.json).is_err(),
            test_case.expected_rejected,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_diagnostic_json_when_parsed_then_sequence_fields_and_correlations_are_kept() {
    let test_cases = [
        DiagnosticTestCase {
            description: "fields and run correlation survive",
            json: r#"{"occurred_at":"2026-10-19T00:00:00.000000Z","severity":"warning",
                "logger":"sqlbuild.x","source":"python","message":"careful","fields":{"k":1},
                "run_id":"r1"}"#,
            sequence: 5,
            expected_fields: r#"{"k":1}"#,
            expected_run_id: Some("r1"),
        },
        DiagnosticTestCase {
            description: "absent fields become an empty object",
            json: r#"{"occurred_at":"2026-10-19T00:00:00.000000Z","severity":"info",
                "logger":"sqlbuild.x","source":"python","message":"hello"}"#,
            sequence: 0,
            expected_fields: "{}",
            expected_run_id: None,
        },
    ];

    for test_case in test_cases {
        let diagnostic = diagnostic_input_from_json(test_case.json, test_case.sequence)
            .expect("the fixture is a valid diagnostic");
        assert_eq!(
            (
                diagnostic.sequence,
                diagnostic.fields.as_str(),
                diagnostic.correlations.run_id.as_deref()
            ),
            (
                test_case.sequence,
                test_case.expected_fields,
                test_case.expected_run_id
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_incomplete_diagnostic_json_when_parsed_then_it_is_rejected() {
    let test_cases = [RejectedInputTestCase {
        description: "a diagnostic needs a message and logger",
        json: r#"{"severity":"info"}"#,
        expected_rejected: true,
    }];

    for test_case in test_cases {
        assert_eq!(
            diagnostic_input_from_json(test_case.json, 0).is_err(),
            test_case.expected_rejected,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_context_and_environment_when_classifying_then_the_origin_is_named() {
    let test_cases = [
        OriginTestCase {
            description: "external context wins over CI",
            has_external_context: true,
            environment: vec![("CI", "true")],
            expected_origin: "integration",
        },
        OriginTestCase {
            description: "a CI system's variable marks CI",
            environment: vec![("GITHUB_ACTIONS", "true")],
            has_external_context: false,
            expected_origin: "ci",
        },
        OriginTestCase {
            description: "a URL value marks CI",
            environment: vec![("JENKINS_URL", "https://ci.example.com/")],
            has_external_context: false,
            expected_origin: "ci",
        },
        OriginTestCase {
            description: "false, 0 and empty values are not CI",
            environment: vec![("CI", "false"), ("GITLAB_CI", "0"), ("BUILDKITE", " ")],
            has_external_context: false,
            expected_origin: "local",
        },
        OriginTestCase {
            description: "no variables is local",
            environment: Vec::new(),
            has_external_context: false,
            expected_origin: "local",
        },
    ];
    for test_case in test_cases {
        let environment = |name: &str| {
            test_case
                .environment
                .iter()
                .find(|(key, _)| *key == name)
                .map(|(_, value)| (*value).to_owned())
        };
        assert_eq!(
            invocation_origin(test_case.has_external_context, environment),
            test_case.expected_origin,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_a_command_and_its_flags_when_naming_its_mode_then_only_debug_has_one() {
    let test_cases = [
        CommandModeTestCase {
            description: "debug without a connection checks configuration only",
            command: Some("debug"),
            no_connection: true,
            expected_mode: Some("config_only"),
        },
        CommandModeTestCase {
            description: "debug also tests the connection",
            command: Some("debug"),
            no_connection: false,
            expected_mode: Some("config_and_connection"),
        },
        CommandModeTestCase {
            description: "other commands record no mode",
            command: Some("build"),
            no_connection: false,
            expected_mode: None,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            command_mode(test_case.command, test_case.no_connection),
            test_case.expected_mode,
            "{}",
            test_case.description
        );
    }
}
