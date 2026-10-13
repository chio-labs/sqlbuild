//! A planned audit's identity inputs, its identity hashes and measurement policies.

/// One directional measurement threshold.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum ThresholdBound {
    Below(f64),
    Above(f64),
    /// Inclusive `(lower, upper)` range whose outside violates.
    Outside(f64, f64),
}

/// A measurement audit's warn and error bounds.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Thresholds {
    pub warn: Option<ThresholdBound>,
    pub error: Option<ThresholdBound>,
}

/// The measurement facts a measurement audit's identity includes.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct MeasurementFacts {
    pub value_column: Option<String>,
    pub sample_count_column: Option<String>,
    pub sample_unit: Option<String>,
    pub thresholds: Option<Thresholds>,
    pub minimum_samples: Option<i64>,
    pub evidence_unresolved_sql: Option<String>,
    pub evidence_resolved_sql: Option<String>,
}

/// One planned audit binding, as its identity reads it.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct PlannedAudit {
    pub name: String,
    pub attachment_kind: String,
    pub attached_target_name: Option<String>,
    pub attached_column_name: Option<String>,
    pub severity: String,
    pub run_scope: String,
    pub always_run: bool,
    pub unresolved_sql: String,
    pub resolved_sql: String,
    /// Present for measurement audits.
    pub measurement: Option<MeasurementFacts>,
}

/// The identity hashes of one planned audit; `index` is its position in the input.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AuditIdentity {
    pub index: usize,
    pub binding_key: String,
    pub definition_fingerprint: String,
    pub execution_fingerprint: String,
}

/// A gate's binding and blocking set hashes, with its audits sorted by binding key.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct GateIdentity {
    pub binding_set_hash: String,
    pub blocking_set_hash: String,
    pub audits: Vec<AuditIdentity>,
}

/// The canonical outcome of one measured value.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MeasurementOutcome {
    Pass,
    Warn,
    Error,
    Insufficient,
}
