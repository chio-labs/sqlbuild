//! Wire values shared with Python's model analysis.

/// The native engine's request for Python's legacy type recovery.
pub(crate) const LEGACY_FALLBACK: &str = "native project type recovery requires legacy fallback";
/// Python logs this for a malformed per-model response.
pub(crate) const INVALID_NATIVE_RESPONSE: &str = "invalid native response";
/// Python's `UNKNOWN` column type.
pub(crate) const UNKNOWN_TYPE: &str = "UNKNOWN";
/// Python's `InferredNullability.UNKNOWN`.
pub(crate) const UNKNOWN_NULLABILITY: &str = "unknown";
/// Python's `InferredNullability` values by native code.
pub(crate) const NULLABILITY_BY_CODE: [&str; 3] = ["unknown", "non_null", "nullable"];
/// The transform and confidence code counts Python's enum tuples accept.
pub(crate) const TRANSFORM_CODES: u64 = 6;
pub(crate) const CONFIDENCE_CODES: u64 = 3;
/// Python's `COMPACT_ANALYSIS_RESPONSE_LENGTH`: a member's `[template, mappings]`.
pub(crate) const RESPONSE_LENGTH: usize = 2;
/// Python's `COMPACT_ANALYSIS_LEGACY_RESPONSE_LENGTH`: `[rows, has_star, flag]`.
pub(crate) const LEGACY_RESPONSE_LENGTH: usize = 3;
/// Python's `COMPACT_ANALYSIS_FACT_LENGTH`.
pub(crate) const FACT_LENGTH: usize = 6;
/// Python's `COMPACT_ANALYSIS_SOURCE_LENGTH`.
pub(crate) const SOURCE_LENGTH: usize = 3;
/// Python's `BINDING_SEVERITIES`.
pub(crate) const BINDING_SEVERITIES: [&str; 2] = ["error", "warning"];
/// Python's default binding message.
pub(crate) const DEFAULT_BINDING_MESSAGE: &str = "SQL binding failed";
/// Analysis workers per compact batch, as Python requests.
pub(crate) const COMPACT_WORKERS: usize = 4;
/// Python's `NATIVE_DIALECT_ALIASES`.
pub(crate) const DIALECT_ALIASES: [(&str, &str); 3] = [
    ("postgres", "postgresql"),
    ("motherduck", "duckdb"),
    ("sqlserver", "tsql"),
];
/// The quote that marks an exact identifier.
pub(crate) const QUOTED_IDENTIFIER_DELIMITER: char = '"';
/// Python's names for a legacy-analysis and an enrichment deferral.
pub(crate) const DEFERRAL_ANALYSIS: &str = "analysis";
pub(crate) const DEFERRAL_ENRICHMENT: &str = "enrichment";
