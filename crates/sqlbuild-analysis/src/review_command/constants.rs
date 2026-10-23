//! Report format, statuses, exit codes, error codes and review schema naming.

/// The version of the review JSON document; additive fields keep it, breaking changes bump it.
pub const REVIEW_REPORT_FORMAT_VERSION: u32 = 1;

pub const MODEL_KIND: &str = "model";
pub const SEED_KIND: &str = "seed";

pub const CRITICAL_POLICY: &str = "critical";
pub const ALL_POLICY: &str = "all";
pub const NONE_POLICY: &str = "none";

pub const PASSED_STATUS: &str = "passed";
pub const FINDINGS_STATUS: &str = "findings";
pub const INCOMPLETE_STATUS: &str = "incomplete";
pub const FAILED_STATUS: &str = "failed";
pub const PLANNED_STATUS: &str = "planned";

pub const PASS_EXIT_CODE: i32 = 0;
pub const FINDINGS_EXIT_CODE: i32 = 1;
pub const INCOMPLETE_EXIT_CODE: i32 = 2;
pub const FAILURE_EXIT_CODE: i32 = 3;

/// Node statuses in the impact tree.
pub const BUILT_NODE: &str = "built";
pub const OK_NODE: &str = "ok";
pub const FINDING_NODE: &str = "finding";
pub const FAILED_NODE: &str = "failed";
pub const NOT_VALIDATED_NODE: &str = "not_validated";

/// A `--select` token that matched no project node.
pub const UNKNOWN_SELECTION_CODE: &str = "C761";
/// A `--select` token that matched only unchanged nodes.
pub const UNCHANGED_SELECTION_CODE: &str = "C762";
/// A `--select` token outside the downstream policy.
pub const OUT_OF_SCOPE_SELECTION_CODE: &str = "C763";
/// Nothing changed since the base revision.
pub const NOTHING_CHANGED_CODE: &str = "C764";

/// The default `[review] schema_prefix`.
pub const DEFAULT_SCHEMA_PREFIX: &str = "REVIEW";
/// The default `[review] critical_tags`.
pub const DEFAULT_CRITICAL_TAG: &str = "critical";
/// Hex digits of the commit and of the invocation in a review schema name.
pub const SCHEMA_COMMIT_DIGITS: usize = 7;
pub const SCHEMA_RUN_DIGITS: usize = 6;
/// Characters of the `YYYYMMDDTHHMMSSZ` timestamp in a review schema name.
pub const SCHEMA_TIMESTAMP_LENGTH: usize = 16;
/// How old a marked review schema must be before the janitor drops it, in seconds.
pub const LEFTOVER_REVIEW_SCHEMA_AGE_SECONDS: i64 = 24 * 60 * 60;

/// The comparison limit of the minimum review: any difference is a finding.
pub const EXACT_LIMIT: &str = "exact match";
/// Example keys shown per finding.
pub const MAX_FINDING_EXAMPLES: usize = 3;
