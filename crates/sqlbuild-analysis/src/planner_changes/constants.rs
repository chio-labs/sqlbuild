//! Planner change-detection constants shared with the Python planner.

/// Fingerprint metadata key of the recorded audit gate.
pub const AUDIT_GATE_METADATA_KEY: &str = "audit_gate";
/// Fingerprint metadata key of the migration fingerprint.
pub const MIGRATION_FINGERPRINT_METADATA_KEY: &str = "migration_fingerprint";
/// Fingerprint metadata key of the declared-columns hash.
pub const DECLARED_COLUMNS_METADATA_KEY: &str = "declared_columns_hash";
/// Fingerprint metadata key of directly called function hashes.
pub const LOCAL_FUNCTION_HASHES_METADATA_KEY: &str = "local_function_hashes";
/// Fingerprint metadata key of the model config.
pub const CONFIG_METADATA_KEY: &str = "config";
/// Model config key of cursor inputs.
pub const CURSOR_INPUTS_CONFIG_KEY: &str = "cursor_inputs";
/// Metadata a fingerprint row without metadata records.
pub const EMPTY_FINGERPRINT_METADATA_JSON: &str = "{}";
/// The replay policy value that replays nothing.
pub const FORWARD_ONLY_POLICY: &str = "forward";
/// The replay policy value that replays everything.
pub const FULL_POLICY: &str = "full";
/// Prefix of a bounded replay policy.
pub const BOUNDED_POLICY_PREFIX: &str = "bounded-";
/// The dialect whose unquoted column names fold to lower case for comparison.
pub const CASE_FOLDING_DIALECT: &str = "snowflake";
/// At most this many rename mappings are tried for one query.
pub const MAX_CANDIDATE_MAPPINGS: usize = 64;
