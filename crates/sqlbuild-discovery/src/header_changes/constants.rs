//! The header keys and values a delta compile can recompile a model for.

/// Header keys a delta compile recompiles the model for; any other changed key falls back.
pub(crate) const PATCHED_KEYS: [&str; 6] = [
    "description",
    "columns",
    "dynamic_columns",
    "model_schema",
    "audits",
    "contract",
];
/// `materialized` values a delta compile handles; others name materializations it cannot.
pub(crate) const PATCHED_MATERIALIZATIONS: [&str; 2] = ["view", "table"];
pub(crate) const MATERIALIZED_KEY: &str = "materialized";
/// Plain `--` comments, which every adapter's SQL reads as comments.
pub(crate) const LINE_COMMENT: &str = "--";
/// Reference call kinds and the upstream kinds they resolve to.
pub(crate) const REF_CALL: &str = "ref";
pub(crate) const SOURCE_CALL: &str = "source";
pub(crate) const SEED_CALL: &str = "seed";
pub(crate) const MODEL_KIND: &str = "model";
pub(crate) const SOURCE_KIND: &str = "source";
pub(crate) const SEED_KIND: &str = "seed";

/// Bytes of a digest kept per header value; a collision would need 2^64 work to find.
pub(crate) const KEPT_DIGEST_BYTES: usize = 16;
pub(crate) const HEX: &[u8; 16] = b"0123456789abcdef";
