use crate::execution_history::main::sqlite_database_path::sqlite_database_path;
use crate::execution_history::main::validate_filter::validate_filter;
use crate::execution_history::models::{
    EventFilterSpec, FilterSpec, RunFilterSpec, SqliteLocation,
};
use crate::execution_history::tests::helpers::bound;
use crate::execution_history::tests::test_types::{FilterTestCase, PathTestCase};

#[test]
fn given_filters_when_validating_then_python_messages_are_returned() {
    let test_cases = [
        FilterTestCase {
            description: "empty filters are valid",
            event_filter: EventFilterSpec::default(),
            run_filter: RunFilterSpec::default(),
            expected_event_error: None,
            expected_run_error: None,
        },
        FilterTestCase {
            description: "Python whitespace counts as blank",
            event_filter: EventFilterSpec {
                producer: Some(" \u{1c}".to_owned()),
                ..EventFilterSpec::default()
            },
            run_filter: RunFilterSpec {
                invocation_id: Some("\t".to_owned()),
                ..RunFilterSpec::default()
            },
            expected_event_error: Some("producer must be non-empty when provided"),
            expected_run_error: Some("invocation_id must be non-empty when provided"),
        },
        FilterTestCase {
            description: "types and family conflict before blank types",
            event_filter: EventFilterSpec {
                event_types: vec![" ".to_owned()],
                family: Some("run".to_owned()),
                ..EventFilterSpec::default()
            },
            run_filter: RunFilterSpec::default(),
            expected_event_error: Some("event_types and family are mutually exclusive"),
            expected_run_error: None,
        },
        FilterTestCase {
            description: "non-UTC and reversed bounds",
            event_filter: EventFilterSpec {
                occurred_at_start: Some(bound(1, false)),
                ..EventFilterSpec::default()
            },
            run_filter: RunFilterSpec {
                created_at_start: Some(bound(2, true)),
                created_at_end: Some(bound(1, true)),
                ..RunFilterSpec::default()
            },
            expected_event_error: Some("occurred_at_start must use UTC"),
            expected_run_error: Some("created_at_start must not be after created_at_end"),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            (
                validate_filter(FilterSpec::Event(&test_case.event_filter))
                    .err()
                    .map(|error| error.message),
                validate_filter(FilterSpec::Run(&test_case.run_filter))
                    .err()
                    .map(|error| error.message),
            ),
            (
                test_case.expected_event_error.map(str::to_owned),
                test_case.expected_run_error.map(str::to_owned),
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_locations_when_resolving_sqlite_path_then_pathlib_normalisation_applies() {
    let test_cases = [
        PathTestCase {
            description: "project directory gets the history file",
            project_dir: Some("/work/project/"),
            path: None,
            busy_timeout_ms: Some(5000),
            expected_path: Ok("/work/project/.sqlbuild/history.sqlite3"),
        },
        PathTestCase {
            description: "explicit path is normalised",
            project_dir: None,
            path: Some("./data//history.db"),
            busy_timeout_ms: Some(5000),
            expected_path: Ok("data/history.db"),
        },
        PathTestCase {
            description: "in-memory database",
            project_dir: None,
            path: Some(":memory:"),
            busy_timeout_ms: Some(5000),
            expected_path: Ok(":memory:"),
        },
        PathTestCase {
            description: "working directory by default",
            project_dir: None,
            path: None,
            busy_timeout_ms: Some(5000),
            expected_path: Ok("/cwd/.sqlbuild/history.sqlite3"),
        },
        PathTestCase {
            description: "both locations conflict",
            project_dir: Some("a"),
            path: Some("b"),
            busy_timeout_ms: None,
            expected_path: Err("provide project_dir or path, not both"),
        },
        PathTestCase {
            description: "non-positive busy timeout",
            project_dir: None,
            path: Some("b"),
            busy_timeout_ms: Some(0),
            expected_path: Err("busy_timeout_ms must be a positive integer"),
        },
    ];

    for test_case in test_cases {
        let location = SqliteLocation {
            project_dir: test_case.project_dir.map(str::to_owned),
            path: test_case.path.map(str::to_owned),
            working_directory: "/cwd".to_owned(),
            busy_timeout_ms: test_case.busy_timeout_ms,
        };
        assert_eq!(
            sqlite_database_path(&location).map_err(|error| error.message),
            test_case
                .expected_path
                .map(str::to_owned)
                .map_err(str::to_owned),
            "{}",
            test_case.description
        );
    }
}
