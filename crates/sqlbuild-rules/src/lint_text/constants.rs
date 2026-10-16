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

/// Bytes every lint and format site pattern match starts with.
pub(crate) const SITE_START_BYTES: [u8; 3] = *b"@$_";
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

pub(crate) const FORMAT_API_VERSION: u32 = 1;
pub(crate) const MAX_FUNCTION_CALL_DEPTH: usize = 512;
pub(crate) const OMITTED_CEREMONIAL_SELECT_SQL: &str = "\nSELECT 1";
pub(crate) const OMITTED_SELECT_SUFFIX_PATTERN: &str = r"(?i)\s*\bSELECT\s+1\s*\z";
pub(crate) const FIXTURE_HEADER_KINDS: [&str; 2] = ["TEST", "SCENARIO"];
pub(crate) const LINE_COMMENT_PREFIX: &str = "--";
pub(crate) const DECLINED_WITHOUT_REASON: &str = "native formatter declined without a reason";
pub(crate) const MOVED_OMITTED_SELECT: &str =
    "native formatter moved the omitted ceremonial SELECT 1";
pub(crate) const DECLARATION_GROUP_DIRECTORY: &str = "_sqlbuild";
/// `GLOBAL_NAMED_DECLARATION_ROOTS`, in Python's dict order, with whether each holds audits.
pub(crate) const GLOBAL_NAMED_ROOTS: [(&[&str], bool); 5] = [
    (&["audits", "generic"], true),
    (&["audits", "singular"], true),
    (&["schemas"], false),
    (&["hooks", "sql"], false),
    (&["hooks", "python"], false),
];
/// `GROUPED_NAMED_DECLARATION_ROLES`, in Python's dict order, with whether each holds audits.
pub(crate) const GROUPED_NAMED_ROLES: [(&[&str], bool); 9] = [
    (&["audits", "generic"], true),
    (&["_audits", "generic"], true),
    (&["audits", "singular"], true),
    (&["schemas"], false),
    (&["_schemas"], false),
    (&["hooks", "sql"], false),
    (&["_hooks", "sql"], false),
    (&["hooks", "python"], false),
    (&["_hooks", "python"], false),
];

pub(crate) const LINT_API_VERSION: i64 = 1;
pub(crate) const UNUSED_CTE_CODE: &str = "SQBRSQL005";
pub(crate) const LONG_LITERAL_CODE: &str = "SQBRSQL044";
pub(crate) const NATIVE_LINT_ERROR_CODE: &str = "L003";
pub(crate) const PARSE_ERROR_POSITION_PATTERN: &str =
    r"^Parse error at line (?P<line>\d+), column (?P<column>\d+):";
pub(crate) const HARNESS_CTE_PREFIXES: [&str; 13] = [
    "__expected__",
    "__assert__",
    "__ref__",
    "__source__",
    "__seed__",
    "__dbt_ref__",
    "__macro__",
    "__macro_actual__",
    "__macro_expected__",
    "__udf_actual__",
    "__udf_expected__",
    "__table_fn_actual__",
    "__table_fn_expected__",
];
pub(crate) const PARSE_FAILURE_PREFIX: &str = "Native SQL parser could not analyze this body: ";
pub(crate) const PARSE_FAILURE_REMEDIATION: &str =
    "Use SQL syntax supported by the native parser or report the parser gap.";
pub(crate) const INVALID_DIAGNOSTIC: &str =
    "native lint diagnostic has invalid code, message, or source span";
pub(crate) const INVALID_FIX_REASON: &str =
    "native lint diagnostic has an invalid fix refusal reason";
pub(crate) const INVALID_FIX_OBJECT: &str = "native lint diagnostic fix must be an object";
pub(crate) const INVALID_FIX_EDIT: &str = "native lint diagnostic has an invalid fix edit";
pub(crate) const NOT_AN_OBJECT: &str = "native lint diagnostic must be an object";
pub(crate) const NON_OBJECT_RESPONSE: &str = "native lint engine returned a non-object response";
pub(crate) const UNSUPPORTED_VERSION: &str =
    "native lint engine returned an unsupported response version";
pub(crate) const MISSING_DIAGNOSTICS: &str = "native lint response is missing a diagnostics list";
pub(crate) const INVALID_BATCH: &str = "native lint engine returned an invalid batch response";
pub(crate) const NON_CONTIGUOUS_FIX: &str =
    "fix overlaps generated SQL or a non-contiguous authored region";
pub(crate) const GENERATED_FIX: &str = "fix overlaps generated SQL";
pub(crate) const GENERATED_SQL_SUFFIX: &str = "(in generated SQL)";
pub(crate) const LOCAL_CONFIG_FILENAME: &str = "sqlbuild_local.toml";
pub(crate) const DEFAULT_LINE_WIDTH: i64 = 100;
pub(crate) const DEFAULT_MAX_DESCRIPTION_LINES: i64 = 10;
pub(crate) const DEFAULT_MAX_LITERAL_LENGTH: i64 = 100;
pub(crate) const DEFAULT_MAX_RANKING_ORDER_BY: i64 = 5;
pub(crate) const DEFAULT_DIALECT: &str = "generic";
/// Adapter names whose SQL dialect has another name; other adapters name their dialect.
pub(crate) const ADAPTER_DIALECT_TRANSLATIONS: [(&str, &str); 2] =
    [("motherduck", "duckdb"), ("sqlserver", "tsql")];
pub(crate) const MODELS_DIRECTORY: &str = "models";
/// Inherited and local declaration folders, whose files declare several headers.
pub(crate) const SCOPED_DECLARATION_DIRECTORIES: [&str; 6] = [
    "macros",
    "enums",
    "constants",
    "_macros",
    "_enums",
    "_constants",
];
/// `GLOBAL_NAMED_DECLARATION_ROOTS`, in Python's dict order, with their declaration kinds.
pub(crate) const GLOBAL_NAMED_ROOT_KINDS: [(&[&str], &str); 5] = [
    (&["audits", "generic"], "audit"),
    (&["audits", "singular"], "singular_audit"),
    (&["schemas"], "schema"),
    (&["hooks", "sql"], "sql_hook"),
    (&["hooks", "python"], "python_hook"),
];
/// `GROUPED_NAMED_DECLARATION_ROLES`, in Python's dict order, with their declaration kinds.
pub(crate) const GROUPED_NAMED_ROLE_KINDS: [(&[&str], &str); 9] = [
    (&["audits", "generic"], "audit"),
    (&["_audits", "generic"], "audit"),
    (&["audits", "singular"], "singular_audit"),
    (&["schemas"], "schema"),
    (&["_schemas"], "schema"),
    (&["hooks", "sql"], "sql_hook"),
    (&["_hooks", "sql"], "sql_hook"),
    (&["hooks", "python"], "python_hook"),
    (&["_hooks", "python"], "python_hook"),
];
