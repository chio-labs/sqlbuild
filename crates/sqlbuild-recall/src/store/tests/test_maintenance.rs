use std::time::Duration;

use crate::records::main::artifact_rows::artifact_rows;
use crate::records::main::heartbeat_row::heartbeat_row;
use crate::records::main::invocation_row::invocation_row;
use crate::records::main::parse_timestamp::parse_timestamp;
use crate::records::models::{ArtifactInput, InvocationContext, OutputStream, RecallValue};
use crate::store::main::maintain_sqlite_store::maintain_sqlite_store;
use crate::store::models::{MaintenanceOutcome, MaintenanceRequest};
use crate::store::tests::helpers::{NOW, chunk, envelope, new_store, rows, shifted, text, write};

fn request(now: &str, budget: Duration) -> MaintenanceRequest {
    MaintenanceRequest {
        now: parse_timestamp(now).expect("now"),
        retention_days: 30,
        owner: "host:1".to_owned(),
        budget,
        envelope: envelope("maintainer", now),
    }
}

fn artifact(digest: &str, seen_at: &str) -> ArtifactInput {
    ArtifactInput {
        digest: digest.to_owned(),
        kind: "sql".to_owned(),
        media_type: "text/x-sql".to_owned(),
        content: b"select 1".to_vec(),
        seen_at: seen_at.to_owned(),
        ref_id: digest.to_owned(),
        role: "executed_sql".to_owned(),
        statement_id: None,
        resource_id: None,
    }
}

#[test]
fn given_expired_recent_and_running_invocations_when_maintained_then_only_expired_rows_go() {
    let (_directory, store) = new_store();
    let old = envelope("old", &shifted(-40 * 86_400));
    let recent = envelope("recent", &shifted(-86_400));
    let old_running = envelope("old_running", &shifted(-40 * 86_400));
    let mut batch = Vec::new();
    for env in [&old, &recent, &old_running] {
        batch.push(invocation_row(env, &InvocationContext::default()));
        batch.push(chunk(env, (0, OutputStream::Stdout, b"x")));
    }
    batch.push(heartbeat_row(
        &old_running,
        (&shifted(-10), &shifted(80)),
        (None, None),
    ));
    batch.extend(artifact_rows(
        &old,
        &artifact("sha256:old", &shifted(-40 * 86_400)),
    ));
    batch.extend(artifact_rows(
        &recent,
        &artifact("sha256:recent", &shifted(-40 * 86_400)),
    ));
    write(&store, &batch);
    let outcome =
        maintain_sqlite_store(&store, &request(NOW, Duration::from_secs(5))).expect("maintenance");
    assert_eq!(
        outcome,
        MaintenanceOutcome {
            ran: true,
            deleted_invocations: 1,
            deleted_artifacts: 1,
            complete: true
        }
    );
    assert_eq!(
        rows(
            &store,
            "SELECT invocation_id FROM recall_output ORDER BY invocation_id"
        ),
        vec![vec![text("old_running")], vec![text("recent")]]
    );
    assert_eq!(
        rows(&store, "SELECT digest FROM recall_artifacts"),
        vec![vec![text("sha256:recent")]]
    );
    let again = maintain_sqlite_store(&store, &request(&shifted(3600), Duration::from_secs(5)))
        .expect("second maintenance");
    assert!(!again.ran, "a claim within 24 hours stops another run");
    let next_day =
        maintain_sqlite_store(&store, &request(&shifted(90_000), Duration::from_secs(5)))
            .expect("next day");
    assert!(next_day.ran);
}

#[test]
fn given_no_budget_when_maintained_then_the_next_run_is_overdue() {
    let (_directory, store) = new_store();
    let old = envelope("old", &shifted(-40 * 86_400));
    write(
        &store,
        &[invocation_row(&old, &InvocationContext::default())],
    );
    let starved = maintain_sqlite_store(&store, &request(NOW, Duration::ZERO)).expect("starved");
    assert!(starved.ran && !starved.complete);
    let overdue = maintain_sqlite_store(&store, &request(&shifted(60), Duration::from_secs(5)))
        .expect("overdue run");
    assert!(overdue.ran && overdue.complete);
    assert_eq!(overdue.deleted_invocations, 1);
    assert_eq!(
        rows(&store, "SELECT COUNT(*) FROM recall_invocations"),
        vec![vec![RecallValue::Integer(0)]]
    );
}
