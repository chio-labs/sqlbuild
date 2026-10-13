//! `build_audit_gate_identity`: a gate's binding and blocking set hashes.

use sqlbuild_core::json::models::JsonValue;

use crate::auditing::_helpers::payloads::{audit_identity, hash_payload, identity_payload};
use crate::auditing::constants::BLOCKING_SEVERITY;
use crate::auditing::models::{AuditIdentity, GateIdentity, PlannedAudit};

/// Hash the planned audits' bindings and blocking executions, sorted by binding key.
pub fn audit_gate_identity(audits: &[PlannedAudit]) -> GateIdentity {
    let mut identities: Vec<AuditIdentity> = audits
        .iter()
        .enumerate()
        .map(|(index, audit)| audit_identity(index, audit))
        .collect();
    identities.sort_by(|left, right| left.binding_key.cmp(&right.binding_key));
    let mut bindings: Vec<JsonValue> = Vec::with_capacity(identities.len());
    let mut blocking: Vec<JsonValue> = Vec::new();
    for identity in &identities {
        let audit: &PlannedAudit = &audits[identity.index];
        bindings.push(identity_payload((identity, audit), false));
        if audit.severity == BLOCKING_SEVERITY {
            blocking.push(identity_payload((identity, audit), true));
        }
    }
    GateIdentity {
        binding_set_hash: hash_payload(&JsonValue::Array(bindings)),
        blocking_set_hash: hash_payload(&JsonValue::Array(blocking)),
        audits: identities,
    }
}
