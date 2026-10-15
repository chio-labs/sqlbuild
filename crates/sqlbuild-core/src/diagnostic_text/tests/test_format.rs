use crate::cli_text::models::CliStyle;
use crate::diagnostic_text::main::format_diagnostic_record::format_diagnostic_record;
use crate::diagnostic_text::models::DiagnosticRecordText;
use crate::diagnostic_text::tests::test_types::DiagnosticRecordTestCase;

#[test]
fn given_log_record_fields_when_formatting_then_matches_console_line() {
    let test_cases = [
        DiagnosticRecordTestCase {
            description: "plain record drops the root logger prefix",
            record: DiagnosticRecordText {
                level_name: "DEBUG".to_owned(),
                logger_name: "sqlbuild.compiler".to_owned(),
                message: "Running SQL".to_owned(),
                ..DiagnosticRecordText::default()
            },
            use_color: false,
            expected_text: "[debug] compiler Running sql",
        },
        DiagnosticRecordTestCase {
            description: "context tokens and rounded duration",
            record: DiagnosticRecordText {
                level_name: "INFO".to_owned(),
                logger_name: "sqlbuild.exec".to_owned(),
                message: "done".to_owned(),
                subject: Some("model".to_owned()),
                name: Some("orders".to_owned()),
                tokens: vec![("phase", "run".to_owned())],
                duration_seconds: Some(1.005),
                ..DiagnosticRecordText::default()
            },
            use_color: true,
            expected_text: "\x1b[2m[info]\x1b[0m model orders phase=run duration=1.00s done",
        },
        DiagnosticRecordTestCase {
            description: "transaction statements stay inline",
            record: DiagnosticRecordText {
                level_name: "DEBUG".to_owned(),
                logger_name: "sqlbuild.sql".to_owned(),
                message: "Executing".to_owned(),
                sql: Some(" commit\n".to_owned()),
                ..DiagnosticRecordText::default()
            },
            use_color: false,
            expected_text: "[debug] sql Executing  commit",
        },
        DiagnosticRecordTestCase {
            description: "other statements sit between separators",
            record: DiagnosticRecordText {
                level_name: "DEBUG".to_owned(),
                logger_name: "other".to_owned(),
                message: String::new(),
                sql: Some("SELECT 1 \n".to_owned()),
                ..DiagnosticRecordText::default()
            },
            use_color: false,
            expected_text: "[debug] other \n--------------------------------------------------------------------------------\nSELECT 1\n--------------------------------------------------------------------------------",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            format_diagnostic_record(
                &test_case.record,
                CliStyle {
                    use_color: test_case.use_color
                }
            ),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}
