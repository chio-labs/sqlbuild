use crate::records::models::RecallValue;
use crate::settings::models::AuditEvidence;
use crate::writer::tests::helpers::{failed_statement_sql, stored_evidence};

fn text(value: &str) -> RecallValue {
    RecallValue::Text(value.to_owned())
}

/// The digest of `[{"order_id":<index>}]` without its prefix.
fn evidence_digest(index: u8) -> RecallValue {
    let content: String = format!("[{{\"order_id\":{index}}}]");
    text(&crate::records::main::sha256_hex::sha256_hex(
        content.as_bytes(),
    ))
}

fn kept(outcome: &str, index: u8) -> Vec<RecallValue> {
    vec![
        text(outcome),
        RecallValue::Integer(0),
        evidence_digest(index),
        RecallValue::Integer(1),
        text("audit_evidence"),
        text(&format!("[{{\"order_id\":{index}}}]")),
    ]
}

fn left_out(outcome: &str) -> Vec<RecallValue> {
    vec![
        text(outcome),
        RecallValue::Integer(0),
        RecallValue::Null,
        RecallValue::Integer(1),
        RecallValue::Null,
        RecallValue::Null,
    ]
}

#[test]
fn given_audit_evidence_settings_when_audits_complete_then_kept_evidence_is_an_artifact_and_none_stays_in_the_event()
 {
    let test_cases = [
        (
            AuditEvidence::WarnAndError,
            vec![kept("error", 1), kept("warn", 0)],
        ),
        (
            AuditEvidence::Error,
            vec![kept("error", 1), left_out("warn")],
        ),
        (
            AuditEvidence::Off,
            vec![left_out("error"), left_out("warn")],
        ),
    ];

    for (setting, expected) in test_cases {
        assert_eq!(stored_evidence(setting), expected, "{setting:?}");
    }
}

#[test]
fn given_statements_sharing_sql_and_a_failed_one_when_recorded_then_text_is_stored_once_and_every_statement_is_referenced()
 {
    assert_eq!(
        failed_statement_sql(),
        vec![vec![
            RecallValue::Integer(2),
            RecallValue::Integer(3),
            RecallValue::Integer(0),
            text("s1,s2,s3"),
        ]]
    );
}
