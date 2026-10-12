use crate::compiled_project::main::legacy_schema_error::legacy_schema_error;
use crate::compiled_project::main::opt_out_position::opt_out_position;
use crate::compiled_project::main::text_position::text_position;
use crate::compiled_project::models::TextPosition;
use crate::compiled_project::tests::helpers::legacy_schema_files;
use crate::compiled_project::tests::test_types::{LegacySchemaTestCase, OptOutPositionTestCase};

#[test]
fn given_text_when_locating_opt_out_then_first_whole_word_key_after_start_is_found() {
    let test_cases = [
        OptOutPositionTestCase {
            description: "header key on the first line",
            text: "MODEL (sql_analysis false);",
            start: 0,
            expected_position: TextPosition { line: 1, column: 8 },
        },
        OptOutPositionTestCase {
            description: "legacy key after a longer identifier",
            text: "[path_defaults.marts]\nmy_sql_analysis = 1\nsql_validation = false\n",
            start: 6,
            expected_position: TextPosition { line: 3, column: 1 },
        },
        OptOutPositionTestCase {
            description: "no key falls back to the start of the file",
            text: "é\nmaterialized = \"view\"",
            start: 0,
            expected_position: TextPosition { line: 1, column: 1 },
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            opt_out_position(test_case.text, test_case.start),
            test_case.expected_position,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_legacy_schema_files_when_matching_model_then_attachment_error_is_returned() {
    let test_cases = [
        LegacySchemaTestCase {
            description: "schema file in another directory",
            schema_files: &[("models/staging/schema.yml", &["orders"])],
            expected_error: None,
        },
        LegacySchemaTestCase {
            description: "root schema file declares the model",
            schema_files: &[("schema.yml", &["orders"])],
            expected_error: Some(
                "Schema file schema.yml declares model 'orders', but model metadata must live in \
                 models/marts/orders.sql MODEL(...). Move description, columns, and audits into \
                 the model header.",
            ),
        },
        LegacySchemaTestCase {
            description: "two schema files declare the model",
            schema_files: &[
                ("models/schema.yml", &["orders"]),
                ("models/marts/schema.yml", &["orders", "customers"]),
            ],
            expected_error: Some(
                "Model file models/marts/orders.sql matched multiple schema.yml declarations: \
                 models/schema.yml, models/marts/schema.yml",
            ),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            legacy_schema_error(
                ("orders", "models/marts/orders.sql"),
                &legacy_schema_files(test_case.schema_files)
            )
            .as_deref(),
            test_case.expected_error,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_character_offset_when_positioning_then_line_and_column_count_characters() {
    let test_cases = [
        OptOutPositionTestCase {
            description: "start of text",
            text: "SELECT 1",
            start: 0,
            expected_position: TextPosition { line: 1, column: 1 },
        },
        OptOutPositionTestCase {
            description: "after a multi-byte character on the second line",
            text: "MODEL ();\né __ref",
            start: 12,
            expected_position: TextPosition { line: 2, column: 3 },
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            text_position(test_case.text, test_case.start),
            test_case.expected_position,
            "{}",
            test_case.description
        );
    }
}
