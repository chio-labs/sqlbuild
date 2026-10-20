//! Diagnostic routing decisions match the Python logging filter and compute log handler.

use crate::diagnostic_routing::main::compute_log_admits::compute_log_admits;
use crate::diagnostic_routing::main::console_summary_line::console_summary_line;
use crate::diagnostic_routing::main::diagnostic_severity::diagnostic_severity;
use crate::diagnostic_routing::main::internal_logger::internal_logger;
use crate::diagnostic_routing::main::project_source_path::project_source_path;
use crate::diagnostic_routing::main::route_admits::route_admits;
use crate::diagnostic_routing::main::sql_digest::sql_digest;
use crate::diagnostic_routing::main::third_party_console_form::third_party_console_form;
use crate::diagnostic_routing::models::{RecordFacts, RouteOptions, ThirdPartyConsoleForm};
use crate::diagnostic_routing::tests::test_types::{
    ComputeLogTestCase, ConsoleFormTestCase, DigestTestCase, InternalLoggerTestCase,
    ProjectSourceTestCase, RouteTestCase, SeverityTestCase, SummaryLineTestCase,
};

const EXTERNAL_DEBUG: RecordFacts = RecordFacts {
    internal: false,
    level: 10,
    has_sql_digest: false,
    has_sql_text: false,
};
const DIGEST_ONLY: RecordFacts = RecordFacts {
    internal: true,
    level: 10,
    has_sql_digest: true,
    has_sql_text: false,
};
const CONSOLE: RouteOptions = RouteOptions {
    internal_only: false,
    allow_internal: true,
    include_sql_text: false,
};

#[test]
fn given_logger_names_when_classifying_then_only_sqlbuild_family_is_internal() {
    let test_cases = [
        InternalLoggerTestCase {
            description: "root",
            name: "sqlbuild",
            expected_internal: true,
        },
        InternalLoggerTestCase {
            description: "child",
            name: "sqlbuild.sql",
            expected_internal: true,
        },
        InternalLoggerTestCase {
            description: "shared prefix without separator",
            name: "sqlbuildx",
            expected_internal: false,
        },
        InternalLoggerTestCase {
            description: "third party",
            name: "other",
            expected_internal: false,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            internal_logger(test_case.name),
            test_case.expected_internal,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_route_options_when_routing_then_family_level_and_sql_rules_apply() {
    let test_cases = [
        RouteTestCase {
            description: "external debug is below INFO",
            options: CONSOLE,
            record: EXTERNAL_DEBUG,
            expected_admitted: false,
        },
        RouteTestCase {
            description: "internal debug reaches a destination allowing internal records",
            options: CONSOLE,
            record: DIGEST_ONLY,
            expected_admitted: true,
        },
        RouteTestCase {
            description: "private SQL route skips digest-only records",
            options: RouteOptions {
                include_sql_text: true,
                ..CONSOLE
            },
            record: DIGEST_ONLY,
            expected_admitted: false,
        },
        RouteTestCase {
            description: "internal records need allow_internal",
            options: RouteOptions {
                allow_internal: false,
                ..CONSOLE
            },
            record: DIGEST_ONLY,
            expected_admitted: false,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            route_admits(test_case.options, test_case.record),
            test_case.expected_admitted,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_compute_log_records_when_admitting_then_sql_without_text_is_dropped_with_text_retention() {
    let test_cases = [
        ComputeLogTestCase {
            description: "external debug is below INFO",
            record: EXTERNAL_DEBUG,
            include_sql_text: false,
            expected_admitted: false,
        },
        ComputeLogTestCase {
            description: "digest-only SQL is kept without text retention",
            record: DIGEST_ONLY,
            include_sql_text: false,
            expected_admitted: true,
        },
        ComputeLogTestCase {
            description: "digest-only SQL is skipped with text retention",
            record: DIGEST_ONLY,
            include_sql_text: true,
            expected_admitted: false,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            compute_log_admits(test_case.record, test_case.include_sql_text),
            test_case.expected_admitted,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_logging_levels_when_mapping_then_severity_names_follow_thresholds() {
    let test_cases = [
        SeverityTestCase {
            description: "below DEBUG",
            level: 5,
            expected_severity: "debug",
        },
        SeverityTestCase {
            description: "between INFO and WARNING",
            level: 25,
            expected_severity: "info",
        },
        SeverityTestCase {
            description: "WARNING",
            level: 30,
            expected_severity: "warning",
        },
        SeverityTestCase {
            description: "ERROR",
            level: 40,
            expected_severity: "error",
        },
        SeverityTestCase {
            description: "above CRITICAL",
            level: 99,
            expected_severity: "critical",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            diagnostic_severity(test_case.level),
            test_case.expected_severity,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_sql_when_digesting_then_prefixed_sha256_hex() {
    let test_cases = [DigestTestCase {
        description: "empty statement",
        sql: "",
        expected_digest: "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    }];

    for test_case in test_cases {
        assert_eq!(
            sql_digest(test_case.sql),
            test_case.expected_digest,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_third_party_levels_when_choosing_console_form_then_only_warnings_and_errors_show() {
    let test_cases = [
        ConsoleFormTestCase {
            description: "INFO stays off the console",
            level: 20,
            expected_form: ThirdPartyConsoleForm::Hidden,
        },
        ConsoleFormTestCase {
            description: "WARNING shows one line",
            level: 30,
            expected_form: ThirdPartyConsoleForm::Summary,
        },
        ConsoleFormTestCase {
            description: "ERROR shows in full",
            level: 40,
            expected_form: ThirdPartyConsoleForm::Full,
        },
        ConsoleFormTestCase {
            description: "CRITICAL shows in full",
            level: 50,
            expected_form: ThirdPartyConsoleForm::Full,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            third_party_console_form(test_case.level),
            test_case.expected_form,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_messages_when_summarizing_then_first_line_remains() {
    let test_cases = [
        SummaryLineTestCase {
            description: "multi-line message keeps its first line",
            message: "token refresh failed  \nTraceback (most recent call last):\n  boom",
            expected_line: "token refresh failed",
        },
        SummaryLineTestCase {
            description: "empty message stays empty",
            message: "",
            expected_line: "",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            console_summary_line(test_case.message),
            test_case.expected_line,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_record_paths_when_classifying_then_only_project_files_outside_packages_are_project() {
    let roots: Vec<String> = vec!["/work/orders_shop".to_owned()];
    let test_cases = [
        ProjectSourceTestCase {
            description: "a project hook file is project code",
            pathname: "/work/orders_shop/hooks/python/logs.py",
            expected_project: true,
        },
        ProjectSourceTestCase {
            description: "a package in a project virtual environment is a library",
            pathname: "/work/orders_shop/.venv/lib/python3.12/site-packages/vendor/client.py",
            expected_project: false,
        },
        ProjectSourceTestCase {
            description: "a sibling directory sharing the prefix is outside the project",
            pathname: "/work/orders_shop_tools/client.py",
            expected_project: false,
        },
        ProjectSourceTestCase {
            description: "the standard library is outside the project",
            pathname: "/usr/lib/python3.12/logging/__init__.py",
            expected_project: false,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            project_source_path(test_case.pathname, &roots),
            test_case.expected_project,
            "{}",
            test_case.description
        );
    }
}
