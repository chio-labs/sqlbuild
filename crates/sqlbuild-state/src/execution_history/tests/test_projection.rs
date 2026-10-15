use crate::execution_history::errors::HistoryErrorKind;
use crate::execution_history::main::project_runs::project_runs;
use crate::execution_history::models::RunRow;
use crate::execution_history::tests::helpers::{at, completed, fact, run_row};
use crate::execution_history::tests::test_types::ProjectionTestCase;

#[test]
fn given_durable_facts_when_projecting_then_runs_follow_python_projection() {
    let started = RunRow {
        started_at: Some(at(10, 5)),
        ..run_row("r1", 1, 1)
    };
    let test_cases = [
        ProjectionTestCase {
            description: "start then completion in storage order, regardless of input order",
            facts: vec![
                fact(2, Some(("r1", "i", "run_completed"))),
                fact(1, Some(("r1", "i", "run_started"))),
            ],
            current: vec![],
            expected_runs: Ok(vec![completed(RunRow {
                last_event_cursor: "c2".to_owned(),
                last_storage_order: 2,
                ..started.clone()
            })]),
        },
        ProjectionTestCase {
            description: "stale and run-less facts are ignored",
            facts: vec![fact(1, Some(("r1", "i", "run_failed"))), fact(3, None)],
            current: vec![run_row("r1", 1, 2)],
            expected_runs: Ok(vec![run_row("r1", 1, 2)]),
        },
        ProjectionTestCase {
            description: "identical duplicates collapse",
            facts: vec![
                fact(1, Some(("r1", "i", "run_started"))),
                fact(1, Some(("r1", "i", "run_started"))),
            ],
            current: vec![],
            expected_runs: Ok(vec![started.clone()]),
        },
        ProjectionTestCase {
            description: "different facts sharing a storage order are inconsistent",
            facts: vec![
                fact(1, Some(("r1", "i", "run_started"))),
                fact(1, Some(("r2", "i", "run_started"))),
            ],
            current: vec![],
            expected_runs: Err(HistoryErrorKind::ProjectionConsistency),
        },
        ProjectionTestCase {
            description: "a run cannot move to another invocation",
            facts: vec![fact(3, Some(("r1", "other", "run_started")))],
            current: vec![run_row("r1", 1, 2)],
            expected_runs: Err(HistoryErrorKind::ProjectionConsistency),
        },
        ProjectionTestCase {
            description: "runs sort by creation time then run id",
            facts: vec![],
            current: vec![run_row("b", 2, 1), run_row("c", 1, 2), run_row("a", 2, 3)],
            expected_runs: Ok(vec![
                run_row("c", 1, 2),
                run_row("a", 2, 3),
                run_row("b", 2, 1),
            ]),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            project_runs(test_case.facts, test_case.current).map_err(|error| error.kind),
            test_case.expected_runs,
            "{}",
            test_case.description
        );
    }
}
