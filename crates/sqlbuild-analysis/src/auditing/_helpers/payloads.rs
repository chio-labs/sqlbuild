//! Python's audit identity payloads as JSON values, and their `json.dumps` SHA-256 hashes.

use sha2::{Digest, Sha256};
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonInteger, JsonValue, StdlibJsonOptions};

use crate::auditing::constants::{
    ABOVE_OPERATOR, BELOW_OPERATOR, MEASUREMENT_MODE, OUTSIDE_OPERATOR,
};
use crate::auditing::models::{AuditIdentity, PlannedAudit, ThresholdBound, Thresholds};
use crate::sql_tokens::main::normalized_query_text::normalized_query_text;

fn text(value: &str) -> JsonValue {
    JsonValue::String(value.to_owned())
}

fn optional_text(value: Option<&str>) -> JsonValue {
    value.map_or(JsonValue::Null, text)
}

fn bound(bound: Option<ThresholdBound>) -> JsonValue {
    let Some(bound) = bound else {
        return JsonValue::Null;
    };
    let entries: Vec<(String, JsonValue)> = match bound {
        ThresholdBound::Outside(lower, upper) => vec![
            ("operator".to_owned(), text(OUTSIDE_OPERATOR)),
            ("lower".to_owned(), JsonValue::Float(lower)),
            ("upper".to_owned(), JsonValue::Float(upper)),
        ],
        ThresholdBound::Below(limit) => vec![
            ("operator".to_owned(), text(BELOW_OPERATOR)),
            ("limit".to_owned(), JsonValue::Float(limit)),
        ],
        ThresholdBound::Above(limit) => vec![
            ("operator".to_owned(), text(ABOVE_OPERATOR)),
            ("limit".to_owned(), JsonValue::Float(limit)),
        ],
    };
    JsonValue::Object(entries)
}

fn thresholds(thresholds: Option<Thresholds>) -> JsonValue {
    let Some(thresholds) = thresholds else {
        return JsonValue::Null;
    };
    JsonValue::Object(vec![
        ("warn".to_owned(), bound(thresholds.warn)),
        ("error".to_owned(), bound(thresholds.error)),
    ])
}

/// `hash_payload`: SHA-256 of `json.dumps(payload, sort_keys=True, separators=(",", ":"))`.
pub(crate) fn hash_payload(payload: &JsonValue) -> String {
    let options: StdlibJsonOptions = StdlibJsonOptions {
        sort_keys: true,
        ..StdlibJsonOptions::new(None).with_separators(",", ":")
    };
    let encoded: String = dumps(payload, &JsonDialect::Stdlib(options)).unwrap_or_default();
    format!("{:x}", Sha256::digest(encoded.as_bytes()))
}

/// The binding payload `audit_identity` hashes into the binding key.
fn binding_entries(audit: &PlannedAudit) -> Vec<(String, JsonValue)> {
    let mut entries: Vec<(String, JsonValue)> = vec![
        ("audit_name".to_owned(), text(&audit.name)),
        ("attachment_kind".to_owned(), text(&audit.attachment_kind)),
        (
            "attached_target_name".to_owned(),
            optional_text(audit.attached_target_name.as_deref()),
        ),
        (
            "attached_column_name".to_owned(),
            optional_text(audit.attached_column_name.as_deref()),
        ),
        ("severity".to_owned(), text(&audit.severity)),
        ("run_scope_phase".to_owned(), text(&audit.run_scope)),
        ("always_run".to_owned(), JsonValue::Bool(audit.always_run)),
    ];
    if let Some(measurement) = &audit.measurement {
        entries.extend([
            ("evaluation_mode".to_owned(), text(MEASUREMENT_MODE)),
            (
                "value_column".to_owned(),
                optional_text(measurement.value_column.as_deref()),
            ),
            (
                "sample_count_column".to_owned(),
                optional_text(measurement.sample_count_column.as_deref()),
            ),
            (
                "sample_unit".to_owned(),
                optional_text(measurement.sample_unit.as_deref()),
            ),
            ("thresholds".to_owned(), thresholds(measurement.thresholds)),
            (
                "minimum_samples".to_owned(),
                measurement
                    .minimum_samples
                    .and_then(|count| JsonInteger::parse(&count.to_string()))
                    .map_or(JsonValue::Null, JsonValue::Integer),
            ),
        ]);
    }
    entries
}

fn optional_sql(sql: Option<&str>) -> JsonValue {
    sql.map_or(JsonValue::Null, |sql| text(&normalized_query_text(sql)))
}

/// `audit_identity`: the binding key and definition and execution fingerprints of one audit.
pub(crate) fn audit_identity(index: usize, audit: &PlannedAudit) -> AuditIdentity {
    let binding: Vec<(String, JsonValue)> = binding_entries(audit);
    let mut definition: Vec<(String, JsonValue)> = binding.clone();
    definition.push((
        "unresolved_sql".to_owned(),
        text(&normalized_query_text(&audit.unresolved_sql)),
    ));
    let mut execution: Vec<(String, JsonValue)> = binding.clone();
    execution.push((
        "resolved_sql".to_owned(),
        text(&normalized_query_text(&audit.resolved_sql)),
    ));
    if let Some(measurement) = &audit.measurement {
        definition.push((
            "evidence_unresolved_sql".to_owned(),
            optional_sql(measurement.evidence_unresolved_sql.as_deref()),
        ));
        execution.push((
            "evidence_resolved_sql".to_owned(),
            optional_sql(measurement.evidence_resolved_sql.as_deref()),
        ));
    }
    AuditIdentity {
        index,
        binding_key: hash_payload(&JsonValue::Object(binding)),
        definition_fingerprint: hash_payload(&JsonValue::Object(definition)),
        execution_fingerprint: hash_payload(&JsonValue::Object(execution)),
    }
}

/// `binding_payload`, plus the fingerprints when `with_fingerprints` (`execution_payload`).
pub(crate) fn identity_payload(
    (identity, audit): (&AuditIdentity, &PlannedAudit),
    with_fingerprints: bool,
) -> JsonValue {
    let mut entries: Vec<(String, JsonValue)> = vec![
        ("binding_key".to_owned(), text(&identity.binding_key)),
        ("audit_name".to_owned(), text(&audit.name)),
        ("severity".to_owned(), text(&audit.severity)),
        ("run_scope_phase".to_owned(), text(&audit.run_scope)),
        ("attachment_kind".to_owned(), text(&audit.attachment_kind)),
        (
            "attached_target_name".to_owned(),
            optional_text(audit.attached_target_name.as_deref()),
        ),
        (
            "attached_column_name".to_owned(),
            optional_text(audit.attached_column_name.as_deref()),
        ),
        ("always_run".to_owned(), JsonValue::Bool(audit.always_run)),
    ];
    if with_fingerprints {
        entries.push((
            "definition_fingerprint".to_owned(),
            text(&identity.definition_fingerprint),
        ));
        entries.push((
            "execution_fingerprint".to_owned(),
            text(&identity.execution_fingerprint),
        ));
    }
    JsonValue::Object(entries)
}
