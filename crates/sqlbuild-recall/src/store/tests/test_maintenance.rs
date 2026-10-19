use crate::records::main::artifact_rows::artifact_rows;
use crate::records::main::heartbeat_row::heartbeat_row;
use crate::records::main::invocation_row::invocation_row;
use crate::records::models::{InvocationContext, OutputStream, RecallRow};
use crate::store::models::MaintenanceOutcome;
use crate::store::tests::helpers::{artifact, chunk, envelope, integer, maintained, shifted, text};
use crate::store::tests::test_types::MaintenanceTestCase;

const FORTY_DAYS: i64 = -40 * 86_400;

#[test]
fn given_expired_recent_and_running_invocations_when_maintained_then_only_expired_rows_go() {
    let old = envelope("old", &shifted(FORTY_DAYS));
    let recent = envelope("recent", &shifted(-86_400));
    let old_running = envelope("old_running", &shifted(FORTY_DAYS));
    let mut mixed: Vec<RecallRow> = [&old, &recent, &old_running]
        .into_iter()
        .flat_map(|env| {
            [
                invocation_row(env, &InvocationContext::default()),
                chunk(env, (0, OutputStream::Stdout, b"x")),
            ]
        })
        .collect();
    mixed.push(heartbeat_row(
        &old_running,
        (&shifted(-10), &shifted(80)),
        (None, None),
        (None, None),
    ));
    mixed.extend(artifact_rows(
        &old,
        &artifact("sha256:old", &shifted(FORTY_DAYS)),
    ));
    mixed.extend(artifact_rows(
        &recent,
        &artifact("sha256:recent", &shifted(FORTY_DAYS)),
    ));
    let ran =
        |deleted_invocations: u64, deleted_artifacts: u64, complete: bool| MaintenanceOutcome {
            ran: true,
            deleted_invocations,
            deleted_artifacts,
            complete,
        };
    let test_cases = [
        MaintenanceTestCase {
            description: "expired idle invocations go while recent and running ones stay",
            batch: mixed.clone(),
            runs: &[(0, 5)],
            sql: "SELECT invocation_id FROM recall_output ORDER BY invocation_id",
            expected_outcomes: vec![ran(1, 1, true)],
            expected_rows: vec![vec![text("old_running")], vec![text("recent")]],
        },
        MaintenanceTestCase {
            description: "artifacts referenced only by expired invocations go",
            batch: mixed.clone(),
            runs: &[(0, 5)],
            sql: "SELECT digest FROM recall_artifacts",
            expected_outcomes: vec![ran(1, 1, true)],
            expected_rows: vec![vec![text("sha256:recent")]],
        },
        MaintenanceTestCase {
            description: "a claim stops another run within a day, and an unfinished run that beat within retention is kept",
            batch: mixed,
            runs: &[(0, 5), (3600, 5), (90_000, 5)],
            sql: "SELECT COUNT(*) FROM recall_invocations",
            expected_outcomes: vec![
                ran(1, 1, true),
                MaintenanceOutcome::default(),
                ran(0, 0, true),
            ],
            expected_rows: vec![vec![integer(2)]],
        },
        MaintenanceTestCase {
            description: "a starved run leaves the next run overdue",
            batch: vec![invocation_row(&old, &InvocationContext::default())],
            runs: &[(0, 0), (60, 5)],
            sql: "SELECT COUNT(*) FROM recall_invocations",
            expected_outcomes: vec![ran(0, 0, false), ran(1, 0, true)],
            expected_rows: vec![vec![integer(0)]],
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            maintained(&test_case.batch, test_case.runs, test_case.sql),
            (test_case.expected_outcomes, test_case.expected_rows),
            "{}",
            test_case.description
        );
    }
}
