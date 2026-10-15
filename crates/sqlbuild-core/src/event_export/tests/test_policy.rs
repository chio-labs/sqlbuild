use crate::event_export::main::lifecycle_export_policy::lifecycle_export_policy;
use crate::event_export::main::sanitized_exception_type::sanitized_exception_type;
use crate::event_export::main::stricter_severity::stricter_severity;
use crate::event_export::models::ExportSeverity;
use crate::event_export::tests::test_types::{
    PolicyTestCase, SanitizationTestCase, StricterSeverityTestCase,
};

#[test]
fn given_catalogued_event_types_when_deriving_policy_then_kind_severity_and_priority_match() {
    let test_cases = [
        PolicyTestCase {
            description: "progress events are debug at the lowest priority",
            event_type: "statement_submitted",
            terminal: false,
            expected_kind: "statement",
            expected_severity: ExportSeverity::Debug,
            expected_priority: 0,
        },
        PolicyTestCase {
            description: "terminal successes are info",
            event_type: "resource_attempt_completed",
            terminal: true,
            expected_kind: "resource",
            expected_severity: ExportSeverity::Info,
            expected_priority: 2,
        },
        PolicyTestCase {
            description: "failures are errors at the highest priority",
            event_type: "invocation_failed",
            terminal: true,
            expected_kind: "invocation",
            expected_severity: ExportSeverity::Error,
            expected_priority: 3,
        },
        PolicyTestCase {
            description: "retries are warnings of their own kind",
            event_type: "retry_scheduled",
            terminal: false,
            expected_kind: "retry",
            expected_severity: ExportSeverity::Warning,
            expected_priority: 1,
        },
    ];

    for test_case in test_cases {
        let policy = lifecycle_export_policy(test_case.event_type, test_case.terminal);
        assert_eq!(
            (policy.kind.as_str(), policy.severity, policy.priority),
            (
                test_case.expected_kind,
                test_case.expected_severity,
                test_case.expected_priority
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_exception_names_when_sanitizing_then_only_bounded_identifier_characters_remain() {
    let test_cases = [
        SanitizationTestCase {
            description: "plain names are unchanged",
            name: "RuntimeError".to_owned(),
            expected_name: "RuntimeError".to_owned(),
        },
        SanitizationTestCase {
            description: "each non-identifier character becomes one underscore",
            name: "Bad-Name!\u{e9}".to_owned(),
            expected_name: "Bad_Name__".to_owned(),
        },
        SanitizationTestCase {
            description: "long names are truncated to 100 characters",
            name: "E".repeat(150),
            expected_name: "E".repeat(100),
        },
        SanitizationTestCase {
            description: "empty names fall back to Exception",
            name: String::new(),
            expected_name: "Exception".to_owned(),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            sanitized_exception_type(&test_case.name),
            test_case.expected_name,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_required_and_optional_minimums_when_narrowing_then_stricter_severity_wins() {
    let test_cases = [
        StricterSeverityTestCase {
            description: "absent optional minimum keeps the required one",
            severities: (ExportSeverity::Info, None),
            expected_severity: ExportSeverity::Info,
        },
        StricterSeverityTestCase {
            description: "stricter optional minimum wins",
            severities: (ExportSeverity::Info, Some(ExportSeverity::Error)),
            expected_severity: ExportSeverity::Error,
        },
        StricterSeverityTestCase {
            description: "looser optional minimum is ignored",
            severities: (ExportSeverity::Warning, Some(ExportSeverity::Debug)),
            expected_severity: ExportSeverity::Warning,
        },
    ];

    for test_case in test_cases {
        let (first, second) = test_case.severities;
        assert_eq!(
            stricter_severity(first, second),
            test_case.expected_severity,
            "{}",
            test_case.description
        );
    }
}
