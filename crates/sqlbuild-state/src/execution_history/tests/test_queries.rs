use crate::execution_history::main::event_page_query::event_page_query;
use crate::execution_history::main::run_page_query::run_page_query;
use crate::execution_history::models::{
    Dialect, EventFilterSpec, RunCursorKey, RunFilterSpec, RunStatus,
};
use crate::execution_history::tests::helpers::{at, bound};
use crate::execution_history::tests::test_types::QueryTestCase;

#[test]
fn given_filters_when_building_page_queries_then_sql_matches_each_backend() {
    let event_filter = EventFilterSpec {
        run_id: Some("r".to_owned()),
        event_types: vec!["a".to_owned(), "b".to_owned()],
        occurred_at_end: Some(bound(2, true)),
        ..EventFilterSpec::default()
    };
    let run_filter = RunFilterSpec {
        statuses: vec![RunStatus::Failed, RunStatus::Completed],
        created_at_start: Some(bound(1, true)),
        ..RunFilterSpec::default()
    };
    let key = RunCursorKey {
        created_at: at(1, 0),
        created_at_text: "2026-01-01T00:00:00.000000+00:00".to_owned(),
        run_id: "r".to_owned(),
    };
    let test_cases = [
        QueryTestCase {
            description: "SQLite events expand IN placeholders",
            query: event_page_query(Dialect::Sqlite, 4, &event_filter, 10),
            expected_sql: "SELECT * FROM lifecycle_event_log WHERE storage_id > ? AND run_id = ? AND event_type IN (?,?) AND occurred_at <= ? ORDER BY storage_id ASC LIMIT ?",
            expected_param_count: 6,
        },
        QueryTestCase {
            description: "PostgreSQL events bind one array",
            query: event_page_query(Dialect::Postgres, 0, &event_filter, 10),
            expected_sql: "SELECT * FROM sqlbuild_lifecycle_event_log WHERE storage_id > %s AND run_id = %s AND event_type = ANY(%s) AND occurred_at <= %s ORDER BY storage_id ASC LIMIT %s",
            expected_param_count: 5,
        },
        QueryTestCase {
            description: "SQLite runs after a cursor compare stored text",
            query: run_page_query(Dialect::Sqlite, Some(&key), &run_filter, 5),
            expected_sql: "SELECT * FROM run_projection WHERE (created_at > ? OR (created_at = ? AND run_id > ?)) AND status IN (?,?) AND created_at >= ? ORDER BY created_at, run_id LIMIT ?",
            expected_param_count: 7,
        },
        QueryTestCase {
            description: "PostgreSQL runs after a cursor compare a row value",
            query: run_page_query(Dialect::Postgres, Some(&key), &run_filter, 5),
            expected_sql: "SELECT * FROM sqlbuild_run_projection WHERE (created_at, run_id) > (%s, %s) AND status = ANY(%s) AND created_at >= %s ORDER BY created_at, run_id LIMIT %s",
            expected_param_count: 5,
        },
        QueryTestCase {
            description: "unfiltered runs have no WHERE clause",
            query: run_page_query(Dialect::Sqlite, None, &RunFilterSpec::default(), 5),
            expected_sql: "SELECT * FROM run_projection ORDER BY created_at, run_id LIMIT ?",
            expected_param_count: 1,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            (test_case.query.sql.as_str(), test_case.query.params.len()),
            (test_case.expected_sql, test_case.expected_param_count),
            "{}",
            test_case.description
        );
    }
}
