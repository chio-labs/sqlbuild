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

/// How a model was compared: not at all, schema only, every row, or a recent cursor window.
pub const NO_COMPARISON_MODE: &str = "none";
pub const SCHEMA_ONLY_MODE: &str = "schema_only";
pub const FULL_COMPARISON_MODE: &str = "full";
pub const BOUNDED_COMPARISON_MODE: &str = "bounded";

/// How a changed incremental model or snapshot starts in the review schema.
pub const CLONE_START: &str = "clone";
pub const FULL_REFRESH_START: &str = "full_refresh";

/// Durations shorter than this print as seconds, longer ones as minutes and seconds.
pub const SECONDS_PER_MINUTE: u64 = 60;

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
/// `--against` holds none of the relations the review compares.
pub const MISSING_AGAINST_CODE: &str = "C774";
/// The `--markdown` report could not be written.
pub const MARKDOWN_WRITE_CODE: &str = "C775";
/// A node sets its own database and the review database is unknown.
pub const UNKNOWN_REVIEW_DATABASE_CODE: &str = "C776";
/// A command-line usage error, such as an unknown option or an invalid choice.
pub const USAGE_ERROR_CODE: &str = "C900";
/// The parser `prog` of `sqb review`, and the option that makes it print JSON.
pub const REVIEW_PROG: &str = "sqb review";
pub const JSON_OPTION: &str = "--json";

/// The default `[review] schema_prefix`.
pub const DEFAULT_SCHEMA_PREFIX: &str = "review";
/// The default `[review] critical_tags`.
pub const DEFAULT_CRITICAL_TAG: &str = "critical";
/// Hex digits of the commit and of the invocation in a review schema name.
pub const SCHEMA_COMMIT_DIGITS: usize = 7;
pub const SCHEMA_RUN_DIGITS: usize = 6;
/// Characters of the `YYYYMMDDTHHMMSSZ` timestamp in a review schema name.
pub const SCHEMA_TIMESTAMP_LENGTH: usize = 16;
/// The largest month, day, hour, minute and second a review schema timestamp accepts.
pub const LAST_MONTH: u32 = 12;
pub const LAST_DAY: u32 = 31;
pub const LAST_HOUR: u32 = 23;
pub const LAST_MINUTE: u32 = 59;
pub const LAST_SECOND: u32 = 59;
/// How old a marked review schema must be before the janitor drops it, in days.
pub const LEFTOVER_REVIEW_SCHEMA_AGE_DAYS: i64 = 1;

/// Finding kinds of failed checks, and the limit they missed.
pub const AUDIT_FINDING: &str = "audit";
pub const TEST_FINDING: &str = "test";
pub const PASSES_LIMIT: &str = "passes";
/// The prefix of a failed unit test in the test counts.
pub const UNIT_TEST_LABEL: &str = "unit test ";

/// The comparison limit of the minimum review: any difference is a finding.
pub const EXACT_LIMIT: &str = "exact match";
/// Example keys shown per finding.
pub const MAX_FINDING_EXAMPLES: usize = 3;
