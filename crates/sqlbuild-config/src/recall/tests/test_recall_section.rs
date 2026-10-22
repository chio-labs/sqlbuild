use crate::models::ConfigValue;
use crate::recall::main::recall_section::recall_section;
use crate::recall::models::RecallSection;
use crate::recall::tests::helpers::{table, text};
use crate::recall::tests::test_types::{InvalidSectionTestCase, ValidSectionTestCase};

#[test]
fn given_valid_sections_when_validated_then_settings_are_typed() {
    let test_cases = [
        ValidSectionTestCase {
            description: "every key is typed and trimmed",
            value: table(&[
                ("enabled", ConfigValue::Bool(false)),
                ("write_connection", text(" history_writer ")),
                ("read_connection", text("history_reader")),
                ("retention", text("720h")),
                ("shutdown_timeout", text("1500ms")),
                ("diagnostics_min_severity", text("debug")),
                ("max_output_bytes", ConfigValue::Integer(4_194_304)),
            ]),
            expected_section: RecallSection {
                enabled: Some(false),
                write_connection: Some("history_writer".to_owned()),
                read_connection: Some("history_reader".to_owned()),
                retention_days: Some(30),
                shutdown_timeout_ms: Some(1500),
                diagnostics_min_severity: Some("debug".to_owned()),
                max_output_bytes: Some(4_194_304),
            },
        },
        ValidSectionTestCase {
            description: "a read connection alone reads shared history",
            value: table(&[("read_connection", text("history_reader"))]),
            expected_section: RecallSection {
                read_connection: Some("history_reader".to_owned()),
                ..RecallSection::default()
            },
        },
        ValidSectionTestCase {
            description: "zero output bytes means record everything",
            value: table(&[("max_output_bytes", ConfigValue::Integer(0))]),
            expected_section: RecallSection {
                max_output_bytes: Some(0),
                ..RecallSection::default()
            },
        },
        ValidSectionTestCase {
            description: "an empty table leaves every setting unset",
            value: table(&[]),
            expected_section: RecallSection::default(),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            recall_section(&test_case.value, "recall"),
            Ok(test_case.expected_section),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_invalid_sections_when_validated_then_the_message_names_the_key() {
    let test_cases = [
        InvalidSectionTestCase {
            description: "output bytes must not be negative",
            value: table(&[("max_output_bytes", ConfigValue::Integer(-1))]),
            label: "recall",
            expected_message_prefix: "recall.max_output_bytes must be",
        },
        InvalidSectionTestCase {
            description: "output bytes must be an integer, not a size string",
            value: table(&[("max_output_bytes", text("2MiB"))]),
            label: "recall",
            expected_message_prefix: "recall.max_output_bytes must be",
        },
        InvalidSectionTestCase {
            description: "the removed connection key names its replacements",
            value: table(&[("connection", text("history"))]),
            label: "targets.prod.recall",
            expected_message_prefix: "targets.prod.recall.connection was replaced by write_connection \
                                      and read_connection: set write_connection = \"history\" and \
                                      read_connection = \"history\"",
        },
        InvalidSectionTestCase {
            description: "unknown keys are listed",
            value: table(&[("mode", text("x"))]),
            label: "recall",
            expected_message_prefix: "recall contains unknown key(s): mode",
        },
        InvalidSectionTestCase {
            description: "retention needs a known unit",
            value: table(&[("retention", text("30x"))]),
            label: "recall",
            expected_message_prefix: "recall.retention must be",
        },
        InvalidSectionTestCase {
            description: "retention hours must be whole days",
            value: table(&[("retention", text("25h"))]),
            label: "recall",
            expected_message_prefix: "recall.retention must be",
        },
        InvalidSectionTestCase {
            description: "retention must be positive",
            value: table(&[("retention", text("0d"))]),
            label: "recall",
            expected_message_prefix: "recall.retention must be",
        },
        InvalidSectionTestCase {
            description: "shutdown timeout is bounded",
            value: table(&[("shutdown_timeout", text("601s"))]),
            label: "recall",
            expected_message_prefix: "recall.shutdown_timeout must be",
        },
        InvalidSectionTestCase {
            description: "severity must be known",
            value: table(&[("diagnostics_min_severity", text("loud"))]),
            label: "recall",
            expected_message_prefix: "recall.diagnostics_min_severity must be one of",
        },
        InvalidSectionTestCase {
            description: "the section must be a table",
            value: text("x"),
            label: "targets.dev.recall",
            expected_message_prefix: "targets.dev.recall must be a table",
        },
    ];

    for test_case in test_cases {
        let message: String = recall_section(&test_case.value, test_case.label)
            .expect_err("the settings are invalid");
        assert!(
            message.starts_with(test_case.expected_message_prefix),
            "{}: {message}",
            test_case.description
        );
    }
}
