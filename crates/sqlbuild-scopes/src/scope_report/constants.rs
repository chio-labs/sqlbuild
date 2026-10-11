//! Section names, policies, labels and messages of scope reports.

pub(crate) const AVAILABLE_SECTION: &str = "available";
pub(crate) const USED_SECTION: &str = "used";
pub(crate) const RELATIONSHIP_SECTION: &str = "relationship_scope";
pub(crate) const NEARBY_SECTION: &str = "nearby_unavailable";
pub(crate) const LIST_SECTION: &str = "list";
pub(crate) const GLOBAL_SUMMARY_POLICY: &str = "summary";
pub(crate) const GLOBAL_USED_POLICY: &str = "used";
pub(crate) const IDENTITY_SEPARATOR: char = ':';
pub(crate) const PATH_SEPARATOR: char = '/';
pub(crate) const WINDOWS_PATH_SEPARATOR: char = '\\';
pub(crate) const CURRENT_PATH: &str = ".";
pub(crate) const GROUP_DIRECTORY: &str = "_sqlbuild";
pub(crate) const INVALID_PATH_TEXT: &str = "<invalid-project-relative-path>";
pub(crate) const DIRECT_CHILD_STEM: &str = "<direct-child>";
pub(crate) const SQL_SUFFIX: &str = ".sql";
pub(crate) const YML_SUFFIX: &str = ".yml";
pub(crate) const YAML_SUFFIX: &str = ".yaml";
pub(crate) const DEPENDENCY_REASON: &str = "dependency";
pub(crate) const LOCAL_CHAIN: &str = "local";
pub(crate) const INHERITED_CHAIN: &str = "inherited";
pub(crate) const GLOBAL_CHAIN: &str = "global";
pub(crate) const ERROR_SEVERITY: &str = "error";
pub(crate) const ESCAPE_CHARACTER: char = '\u{1b}';
pub(crate) const ENUM_MEMBER_PREVIEW: usize = 20;
pub(crate) const RESULT_SCHEMA_VERSION: i64 = 2;
pub(crate) const METADATA_SCHEMA_VERSION: i64 = 3;
pub(crate) const PROSPECTIVE_USAGE_MESSAGE: &str =
    "Runtime usage and relationship facts are unavailable for a prospective path";

/// Python's `ScopeDiagnosticCode` values the reports raise.
pub(crate) const UNKNOWN_TARGET: &str = "S001";
pub(crate) const UNQUALIFIED_TARGET: &str = "S002";
pub(crate) const DUPLICATE_DECLARATION: &str = "S003";
pub(crate) const INVALID_PROSPECTIVE_PATH: &str = "S011";
pub(crate) const INCOMPLETE_USAGE: &str = "S013";
pub(crate) const INVALID_CURSOR: &str = "S014";
pub(crate) const DUPLICATE_RESOURCE: &str = "S018";
