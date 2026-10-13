//! Sentinel spellings, suppression texts and fixture-null markers.

/// Sentinel standing in for one interpolation site in lint and format SQL.
pub const LINT_SENTINEL_PREFIX: &str = "__sqb_lint_";
pub(crate) const SENTINEL_SUFFIX: &str = "__";
pub(crate) const AUDIT_PARAMETER_SENTINEL_PREFIX: &str = "__sqlbuild_audit_parameter_";
pub(crate) const CONTEXT_SENTINEL_PREFIX: &str = "__sqlbuild_context_parameter_";
pub(crate) const CONTEXT_INTERPOLATION_TOKEN: &str = "@@CTX:";

/// Every SQLBuild intrinsic call protected while formatting.
pub(crate) const FUNCTION_NAMES: [&str; 9] = [
    "__cursor_end",
    "__cursor_start",
    "__dbt_ref",
    "__empty_fixture",
    "__ref",
    "__seed",
    "__source",
    "__table_fn",
    "__udf",
];

pub(crate) const LINT_SITE_PATTERN: &str =
    r"^(?:@@|\$\{|@|(?:__dbt_ref|__ref|__seed|__source|__table_fn|__udf)\()";
pub(crate) const FORMAT_SITE_PATTERN: &str = r"(?i)^(?:@@|\$\{|@|(?:__cursor_end|__cursor_start|__dbt_ref|__empty_fixture|__ref|__seed|__source|__table_fn|__udf)\s*\()";

/// Diagnostic code of every suppression finding.
pub const SUPPRESSION_CODE: &str = "SQBRSQL000";
pub(crate) const SUPPRESSION_PREFIX: &str = "sqb: ignore";
pub(crate) const SUPPRESSION_PATTERN: &str =
    r"^\s*--\s*sqb:\s*ignore\s+(?P<code>[A-Za-z0-9_-]+)\s+because\s+(?P<reason>\S.*)\s*$";
pub(crate) const NATIVE_RULE_PREFIX: &str = "SQBRSQL";
pub(crate) const INVALID_MESSAGE: &str = "Suppression directive is invalid";
pub(crate) const INVALID_REMEDIATION: &str = "Use '-- sqb: ignore CODE because <reason>'.";
pub(crate) const UNUSED_REMEDIATION: &str = "Remove the stale suppression directive.";
pub(crate) const FORBIDDEN_MESSAGE: &str =
    "Inline Rule suppressions are not allowed in this project";
pub(crate) const FORBIDDEN_REMEDIATION: &str = "Remove the directive and fix the finding it suppresses; sqlbuild_project.toml sets [rules] allow_exceptions = false. To allow inline suppressions, set this in sqlbuild_project.toml:\n            [rules]\n            allow_exceptions = true";
pub(crate) const FORBIDDEN_FIX_REASON: &str =
    "removing the directive exposes the finding it suppresses";
pub(crate) const REASON_REQUIRED_FIX_REASON: &str =
    "a valid suppression reason requires user intent";

pub(crate) const FIXTURE_TYPED_NULL_PATTERN: &str = r"(?i)(?:CAST\s*\(\s*NULL\s+AS\b|NULL\s*::)";
pub(crate) const MODEL_FIXTURE_PATTERN: &str =
    r"(?i)\b__ref__(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s+AS\s*\(";
pub(crate) const FIXTURE_CTE_MARKERS: [&str; 3] = ["__ref__", "__source__", "__seed__"];
pub(crate) const IGNORED_SEARCH_DIRECTORIES: [&str; 4] =
    [".git", ".venv", "target", "node_modules"];
pub(crate) const UNIT_TEST_ROOT: [&str; 2] = ["tests", "unit"];
pub(crate) const SQL_SUFFIX: &str = ".sql";
