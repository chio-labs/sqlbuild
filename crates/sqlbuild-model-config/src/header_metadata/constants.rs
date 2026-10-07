//! Authored MODEL header metadata keys the native parser recognises.

/// Keys one MODEL column mapping may declare.
pub const MODEL_COLUMN_KEYS: [&str; 5] =
    ["type", "nullable", "description", "audits", "migrate_from"];
/// Audit options that are not passed to the audit as arguments.
pub const AUDIT_OPTION_KEYS: [&str; 8] = [
    "name",
    "description",
    "severity",
    "run_scope",
    "always_run",
    "thresholds",
    "minimum_samples",
    "evidence_limit",
];
/// Audit severities a header may name.
pub const AUDIT_SEVERITIES: [&str; 2] = ["warn", "error"];
/// The audit that contradicts `nullable = true`.
pub const NOT_NULL_AUDIT_NAME: &str = "not_null";
