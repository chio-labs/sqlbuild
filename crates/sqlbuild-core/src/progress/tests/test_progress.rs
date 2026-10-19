use crate::progress::models::{ProgressEvent, ProgressPayload, ProgressSettings};
use crate::progress::tests::helpers::{
    attempt_event, audit_rows, operation_event, orders_claim, plain, project_case,
};
use crate::progress::tests::test_types::{AuditRowTestCase, ProjectionTestCase};

#[test]
fn given_lifecycle_facts_when_projecting_then_progress_lines_match() {
    let test_cases = [
        ProjectionTestCase {
            description: "an unenriched attempt renders its start and terminal once",
            settings: plain(),
            enriched: vec![],
            events: vec![
                attempt_event("e1", "resource_attempt_started", ("a1", None)),
                attempt_event("e2", "resource_attempt_completed", ("a1", Some(1234.0))),
                attempt_event("e2", "resource_attempt_completed", ("a1", Some(1234.0))),
            ],
            claims: vec![],
            expected_lines: vec!["  table     orders START", "  table     orders OK 1.23s"],
            expected_durations: vec![],
        },
        ProjectionTestCase {
            description: "an enriched terminal is claimed and earlier attempts render first",
            settings: plain(),
            enriched: vec!["orders"],
            events: vec![
                attempt_event("e1", "resource_attempt_failed", ("a1", Some(10.0))),
                attempt_event("e2", "resource_attempt_completed", ("a2", Some(20.0))),
            ],
            claims: vec![orders_claim(), orders_claim()],
            expected_lines: vec!["  table     orders FAIL 0.01s"],
            expected_durations: vec![Some(20.0), None],
        },
        ProjectionTestCase {
            description: "an unclaimed enriched terminal renders on close",
            settings: plain(),
            enriched: vec!["orders"],
            events: vec![attempt_event(
                "e1",
                "resource_attempt_skipped",
                ("a1", None),
            )],
            claims: vec![],
            expected_lines: vec!["  table     orders SKIP"],
            expected_durations: vec![],
        },
        ProjectionTestCase {
            description: "a terminal stream leaves starts to live rows",
            settings: ProgressSettings {
                is_tty: true,
                ..plain()
            },
            enriched: vec![],
            events: vec![
                attempt_event("e1", "resource_attempt_started", ("a1", None)),
                operation_event("o1", "operation_started", ("project_compile", None)),
                operation_event("o2", "operation_completed", ("project_compile", None)),
            ],
            claims: vec![],
            expected_lines: vec![],
            expected_durations: vec![],
        },
        ProjectionTestCase {
            description: "a top-level operation renders its start and terminal",
            settings: plain(),
            enriched: vec![],
            events: vec![
                operation_event("o1", "operation_started", ("project_compile", None)),
                operation_event("o2", "operation_failed", ("project_compile", None)),
            ],
            claims: vec![],
            expected_lines: vec!["Project compile  START", "Project compile  FAIL  (1.50s)"],
            expected_durations: vec![],
        },
        ProjectionTestCase {
            description: "a quiet resource operation renders only its failure",
            settings: plain(),
            enriched: vec!["orders"],
            events: vec![
                attempt_event("e1", "resource_attempt_started", ("a1", None)),
                operation_event("o1", "operation_started", ("staging_creation", Some("a1"))),
                operation_event("o2", "operation_failed", ("staging_creation", Some("a1"))),
            ],
            claims: vec![],
            expected_lines: vec![
                "  table     orders START",
                "    Create staging relation  FAIL  (1.50s)",
            ],
            expected_durations: vec![],
        },
        ProjectionTestCase {
            description: "freshness metadata and retries render their details",
            settings: plain(),
            enriched: vec![],
            events: vec![
                operation_event(
                    "o1",
                    "operation_started",
                    ("source_freshness_metadata_observation", None),
                ),
                ProgressEvent {
                    payload: ProgressPayload {
                        metadata_item_count: Some(1),
                        metadata_unknown_count: Some(1),
                        ..operation_event(
                            "o2",
                            "operation_completed",
                            ("source_freshness_metadata_observation", None),
                        )
                        .payload
                    },
                    ..operation_event(
                        "o2",
                        "operation_completed",
                        ("source_freshness_metadata_observation", None),
                    )
                },
                ProgressEvent {
                    payload: ProgressPayload {
                        failed_attempt_number: Some(1),
                        next_attempt_number: Some(2),
                        delay_ms: Some(250.0),
                        ..ProgressPayload::default()
                    },
                    ..attempt_event("r1", "retry_scheduled", ("a1", None))
                },
            ],
            claims: vec![],
            expected_lines: vec![
                "Freshness metadata  START",
                "Freshness metadata  OK (1 source, 1 unknown)  (1.50s)",
                "    retry 1->2 in 0.25s",
            ],
            expected_durations: vec![],
        },
        ProjectionTestCase {
            description: "debug statements render start, query id, heartbeat and failure",
            settings: ProgressSettings {
                debug: true,
                ..plain()
            },
            enriched: vec![],
            events: vec![
                attempt_event("e1", "resource_attempt_started", ("a1", None)),
                ProgressEvent {
                    statement_id: Some("s1".to_owned()),
                    payload: ProgressPayload {
                        intent: "execute".to_owned(),
                        statement_kind: "CREATE".to_owned(),
                        ..ProgressPayload::default()
                    },
                    ..attempt_event("s-start", "statement_started", ("a1", None))
                },
                ProgressEvent {
                    statement_id: Some("s1".to_owned()),
                    payload: ProgressPayload {
                        query_id: Some("q1".to_owned()),
                        intent: "execute".to_owned(),
                        statement_kind: "CREATE".to_owned(),
                        ..ProgressPayload::default()
                    },
                    ..attempt_event("s-sub", "statement_submitted", ("a1", None))
                },
                ProgressEvent {
                    statement_id: Some("s1".to_owned()),
                    payload: ProgressPayload {
                        duration_ms: Some(31000.0),
                        intent: "execute".to_owned(),
                        statement_kind: "CREATE".to_owned(),
                        ..ProgressPayload::default()
                    },
                    ..attempt_event("s-hb", "statement_heartbeat", ("a1", None))
                },
                ProgressEvent {
                    statement_id: Some("s1".to_owned()),
                    payload: ProgressPayload {
                        intent: "execute".to_owned(),
                        statement_kind: "CREATE".to_owned(),
                        ..ProgressPayload::default()
                    },
                    ..attempt_event("s-fail", "statement_failed", ("a1", None))
                },
            ],
            claims: vec![],
            expected_lines: vec![
                "  table     orders START",
                "    statement  model=orders  phase=execute  kind=CREATE  START",
                "    statement  model=orders  phase=execute  kind=CREATE  query_id=q1",
                "    statement  model=orders  phase=execute  kind=CREATE  RUNNING 31.0s  query_id=q1",
                "    statement  model=orders  phase=execute  kind=CREATE  FAIL  query_id=q1",
            ],
            expected_durations: vec![],
        },
    ];

    for test_case in test_cases {
        let (lines, durations) = project_case(&test_case);
        assert_eq!(
            (lines, durations),
            (
                test_case
                    .expected_lines
                    .iter()
                    .map(|line| (*line).to_owned())
                    .collect::<Vec<String>>(),
                test_case.expected_durations
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_standalone_audit_when_projecting_then_row_names_target_and_outcome() {
    let test_cases = [
        AuditRowTestCase {
            description: "a seed column audit names its target and passes",
            resource_id: "audit:not_null:seed:customers:customer_id",
            terminal_event: "resource_attempt_completed",
            recorded_outcomes: vec![("a1", "pass")],
            expected_lines: vec![
                "  audit     not_null (customers.customer_id) START",
                "  audit     not_null (customers.customer_id) PASS 0.01s",
            ],
        },
        AuditRowTestCase {
            description: "a completed audit with a warn outcome shows WARN",
            resource_id: "audit:not_null:source:raw_orders:order_id",
            terminal_event: "resource_attempt_completed",
            recorded_outcomes: vec![("a1", "warn")],
            expected_lines: vec![
                "  audit     not_null (raw_orders.order_id) START",
                "  audit     not_null (raw_orders.order_id) WARN 0.01s",
            ],
        },
        AuditRowTestCase {
            description: "a failed singular audit has no target and shows FAIL",
            resource_id: "audit:not_null:singular",
            terminal_event: "resource_attempt_failed",
            recorded_outcomes: vec![("a1", "error")],
            expected_lines: vec![
                "  audit     not_null START",
                "  audit     not_null FAIL 0.01s",
            ],
        },
        AuditRowTestCase {
            description: "a completed audit without its own recorded outcome passes",
            resource_id: "audit:not_null:model:orders",
            terminal_event: "resource_attempt_completed",
            recorded_outcomes: vec![("a2", "warn")],
            expected_lines: vec![
                "  audit     not_null (orders) START",
                "  audit     not_null (orders) PASS 0.01s",
            ],
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            audit_rows(&test_case),
            test_case.expected_lines,
            "{}",
            test_case.description
        );
    }
}
