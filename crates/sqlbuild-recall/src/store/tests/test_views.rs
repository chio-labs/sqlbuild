use crate::records::main::artifact_rows::artifact_rows;
use crate::records::main::delivery_row::delivery_row;
use crate::records::main::heartbeat_row::heartbeat_row;
use crate::records::main::invocation_row::invocation_row;
use crate::records::models::{
    ArtifactInput, DeliveryCounts, InvocationContext, OutputStream, RecallValue,
};
use crate::store::tests::helpers::{
    NOW, chunk, envelope, event, new_store, rows, text, wall_clock, write,
};

fn delivered(filtered: u64, dropped: u64, delivered: u64) -> DeliveryCounts {
    DeliveryCounts {
        accepted: delivered + filtered + dropped,
        delivered,
        filtered,
        dropped,
        ..DeliveryCounts::default()
    }
}

#[test]
fn given_output_with_and_without_gaps_when_projected_then_completeness_is_exact() {
    let (_directory, store) = new_store();
    let complete = envelope("complete", NOW);
    let gap = envelope("gap", NOW);
    let filtered = envelope("filtered", NOW);
    let undelivered = envelope("no_delivery", NOW);
    for env in [&complete, &gap, &filtered, &undelivered] {
        let sequences: &[u64] =
            if env.invocation_id == "complete" || env.invocation_id == "no_delivery" {
                &[0, 1, 2]
            } else {
                &[0, 2]
            };
        for sequence in sequences {
            write(
                &store,
                &[chunk(env, (*sequence, OutputStream::Stdout, b"x"))],
            );
        }
    }
    write(
        &store,
        &[
            delivery_row(&complete, "output", (&delivered(0, 0, 3), true), NOW),
            delivery_row(&gap, "output", (&delivered(0, 0, 2), true), NOW),
            delivery_row(&filtered, "output", (&delivered(1, 0, 2), true), NOW),
        ],
    );
    let projected = rows(
        &store,
        "SELECT invocation_id, chunks, missing_sequences, filtered, gap_reason, complete \
         FROM output_invocations ORDER BY invocation_id",
    );
    assert_eq!(
        projected,
        vec![
            vec![
                text("complete"),
                RecallValue::Integer(3),
                RecallValue::Integer(0),
                RecallValue::Integer(0),
                RecallValue::Null,
                RecallValue::Integer(1)
            ],
            vec![
                text("filtered"),
                RecallValue::Integer(2),
                RecallValue::Integer(1),
                RecallValue::Integer(1),
                text("filtered"),
                RecallValue::Integer(0)
            ],
            vec![
                text("gap"),
                RecallValue::Integer(2),
                RecallValue::Integer(1),
                RecallValue::Integer(0),
                text("unexplained"),
                RecallValue::Integer(0)
            ],
            vec![
                text("no_delivery"),
                RecallValue::Integer(3),
                RecallValue::Integer(0),
                RecallValue::Integer(0),
                RecallValue::Null,
                RecallValue::Integer(0)
            ],
        ]
    );
}

#[test]
fn given_binary_interleaved_output_when_reconstructed_then_transcripts_are_byte_exact() {
    let (_directory, store) = new_store();
    let env = envelope("binary", NOW);
    let pieces: [(OutputStream, &[u8]); 4] = [
        (OutputStream::Stdout, b"line one\n\x00\xff"),
        (OutputStream::Stderr, b"warn \xe2\x9c\x93\n"),
        (OutputStream::Stdout, b"\xc3\x28 tail"),
        (OutputStream::Stderr, b"\x00end"),
    ];
    // Written out of order: the view orders by sequence, not by insertion.
    for (sequence, (stream, data)) in pieces.iter().enumerate().rev() {
        write(&store, &[chunk(&env, (sequence as u64, *stream, data))]);
    }
    let transcript = rows(
        &store,
        "SELECT stdout, stderr, combined FROM output_transcripts WHERE invocation_id = 'binary'",
    );
    let stdout: Vec<u8> = [pieces[0].1, pieces[2].1].concat();
    let stderr: Vec<u8> = [pieces[1].1, pieces[3].1].concat();
    let combined: Vec<u8> = pieces.iter().flat_map(|(_, data)| data.to_vec()).collect();
    assert_eq!(
        transcript,
        vec![vec![
            RecallValue::Blob(stdout),
            RecallValue::Blob(stderr),
            RecallValue::Blob(combined)
        ]]
    );
    let tail = rows(
        &store,
        "SELECT COUNT(*) FROM output_tail WHERE invocation_id = 'binary'",
    );
    assert_eq!(tail, vec![vec![RecallValue::Integer(4)]]);
}

#[test]
fn given_duplicates_and_conflicts_when_written_then_first_row_is_kept_and_conflicts_reported() {
    let (_directory, store) = new_store();
    let env = envelope("dup", NOW);
    let original = chunk(&env, (0, OutputStream::Stdout, b"first"));
    let conflicting = chunk(&env, (0, OutputStream::Stdout, b"second"));
    write(&store, std::slice::from_ref(&original));
    let duplicate = crate::store::main::insert_rows::insert_rows(&store, &[original], NOW)
        .expect("duplicate is a no-op");
    assert!(duplicate.conflicts.is_empty());
    let conflict = crate::store::main::insert_rows::insert_rows(&store, &[conflicting], NOW)
        .expect("conflict does not fail");
    assert_eq!(conflict.conflicts.len(), 1);
    assert_eq!(conflict.conflicts[0].record_key, "dup:0");
    assert_eq!(
        rows(&store, "SELECT data FROM recall_output"),
        vec![vec![RecallValue::Blob(b"first".to_vec())]]
    );
    assert_eq!(
        rows(
            &store,
            "SELECT invocation_id, dataset, record_key FROM conflicts"
        ),
        vec![vec![text("dup"), text("recall_output"), text("dup:0")]]
    );
}

#[test]
fn given_terminals_and_heartbeats_when_projected_then_status_never_claims_false_success() {
    let (_directory, store) = new_store();
    let done = envelope("done", NOW);
    let failed = envelope("failed_late", NOW);
    let running = envelope("running", NOW);
    let abandoned = envelope("abandoned", "2026-10-01T12:00:00.000000Z");
    let unknown = envelope("unknown", NOW);
    let mut batch = vec![
        event(
            &done,
            ("d0", "invocation_started", 0),
            "",
            r#"{"command":"build"}"#,
        ),
        event(
            &done,
            ("d1", "invocation_completed", 9),
            "",
            r#"{"command":"build","duration_ms":12.5,"exit_code":0}"#,
        ),
        event(
            &failed,
            ("f1", "invocation_completed", 3),
            "",
            r#"{"command":"build","exit_code":0}"#,
        ),
        event(
            &failed,
            ("f2", "invocation_failed", 4),
            "",
            r#"{"command":"build","exit_code":1}"#,
        ),
        event(
            &unknown,
            ("u0", "invocation_started", 0),
            "",
            r#"{"command":"run"}"#,
        ),
        invocation_row(
            &running,
            &InvocationContext {
                command: Some("build".to_owned()),
                target: Some("dev".to_owned()),
                ..InvocationContext::default()
            },
        ),
        heartbeat_row(
            &running,
            (&wall_clock(-1), &wall_clock(90)),
            (None, Some(1)),
        ),
    ];
    batch.push(heartbeat_row(
        &abandoned,
        ("2026-10-01T12:00:30.000000Z", "2026-10-01T12:02:00.000000Z"),
        (None, None),
    ));
    batch.push(heartbeat_row(
        &abandoned,
        ("2026-10-01T12:00:00.000000Z", "2026-10-01T12:01:30.000000Z"),
        (None, None),
    ));
    write(&store, &batch);
    let projected = rows(
        &store,
        "SELECT invocation_id, status, ended_at, duration_ms, exit_code, command, target \
         FROM invocations ORDER BY invocation_id",
    );
    assert_eq!(
        projected,
        vec![
            vec![
                text("abandoned"),
                text("abandoned"),
                text("2026-10-01T12:00:30.000000Z"),
                RecallValue::Real(30000.0),
                RecallValue::Null,
                RecallValue::Null,
                RecallValue::Null
            ],
            vec![
                text("done"),
                text("completed"),
                text(NOW),
                RecallValue::Real(12.5),
                RecallValue::Integer(0),
                text("build"),
                RecallValue::Null
            ],
            vec![
                text("failed_late"),
                text("failed"),
                text(NOW),
                RecallValue::Null,
                RecallValue::Integer(1),
                RecallValue::Null,
                RecallValue::Null
            ],
            vec![
                text("running"),
                text("running"),
                RecallValue::Null,
                RecallValue::Null,
                RecallValue::Null,
                text("build"),
                text("dev")
            ],
            vec![
                text("unknown"),
                text("unknown"),
                RecallValue::Null,
                RecallValue::Null,
                RecallValue::Null,
                text("run"),
                RecallValue::Null
            ],
        ]
    );
}

#[test]
fn given_statement_facts_when_projected_then_failures_and_missing_terminals_stay_visible() {
    let (_directory, store) = new_store();
    let env = envelope("stmts", NOW);
    let sql = "select 1";
    let digest = crate::records::main::sha256_hex::sha256_hex(sql.as_bytes());
    let payload = format!(
        r#"{{"intent":"execute","statement_kind":"SELECT","purpose":"state_write","sql_digest":"{digest}"}}"#
    );
    let failed_payload = format!(
        r#"{{"intent":"execute","statement_kind":"SELECT","sql_digest":"{digest}","error_type":"DatabaseError","error_code":"42P01","query_id":"q9"}}"#
    );
    let mut batch = vec![
        event(
            &env,
            ("r0", "resource_attempt_started", 0),
            r#","run_id":"run","resource_id":"orders","resource_attempt_id":"a1""#,
            r#"{"attempt_number":1,"resource_kind":"model","resource_name":"orders"}"#,
        ),
        event(
            &env,
            ("s0", "statement_started", 1),
            r#","statement_id":"s1","resource_id":"orders""#,
            &payload,
        ),
        event(
            &env,
            ("s1", "statement_failed", 2),
            r#","statement_id":"s1","resource_id":"orders""#,
            &failed_payload,
        ),
        event(
            &env,
            ("s2", "statement_started", 3),
            r#","statement_id":"s2""#,
            r#"{"intent":"query","statement_kind":"SELECT"}"#,
        ),
    ];
    batch.extend(artifact_rows(
        &env,
        &ArtifactInput {
            digest: format!("sha256:{digest}"),
            kind: "sql".to_owned(),
            media_type: "text/x-sql".to_owned(),
            content: sql.as_bytes().to_vec(),
            seen_at: NOW.to_owned(),
            ref_id: "s1".to_owned(),
            role: "executed_sql".to_owned(),
            statement_id: Some("s1".to_owned()),
            resource_id: Some("orders".to_owned()),
        },
    ));
    write(&store, &batch);
    let projected = rows(
        &store,
        "SELECT statement_id, resource_name, purpose, outcome, error_code, query_id, sql_available \
         FROM statements ORDER BY statement_id",
    );
    assert_eq!(
        projected,
        vec![
            vec![
                text("s1"),
                text("orders"),
                text("state_write"),
                text("failed"),
                text("42P01"),
                text("q9"),
                RecallValue::Integer(1)
            ],
            vec![
                text("s2"),
                RecallValue::Null,
                RecallValue::Null,
                text("no_terminal"),
                RecallValue::Null,
                RecallValue::Null,
                RecallValue::Integer(0)
            ],
        ]
    );
    assert_eq!(
        rows(&store, "SELECT available, text FROM artifacts"),
        vec![vec![RecallValue::Integer(1), text(sql)]]
    );
}

#[test]
fn given_audit_completed_facts_when_projected_then_audit_results_carry_outcome_and_target() {
    let (_directory, store) = new_store();
    let env = envelope("audits", NOW);
    write(
        &store,
        &[event(
            &env,
            ("a0", "audit_completed", 1),
            r#","run_id":"run""#,
            r#"{"audit_name":"revenue_positive","audit_definition_name":"positive","evaluation_mode":"violations","outcome":"warn","severity":"warn","run_scope_phase":"model","attachment_kind":"column","target_schema":"analytics","target_name":"daily_revenue","attached_column_name":"total_revenue_cents","violation_count":3,"sql_digest":"ab"}"#,
        )],
    );
    assert_eq!(
        rows(
            &store,
            "SELECT audit_name, target_relation, \"column\", outcome, violation_count FROM audit_results"
        ),
        vec![vec![
            text("revenue_positive"),
            text("analytics.daily_revenue"),
            text("total_revenue_cents"),
            text("warn"),
            RecallValue::Integer(3)
        ]]
    );
}
