//! The `--since` ref alias, git invocation details and error codes.

/// The `--since` value that reads `[git] base_ref` from the project configuration.
pub const BASE_REF_ALIAS: &str = "@base";
/// Hex digits of a commit hash shown in progress and summaries.
pub const SHORT_COMMIT_LENGTH: usize = 10;

/// Python dependency manifests and lock files, by exact name.
pub(crate) const DEPENDENCY_FILE_NAMES: [&str; 5] = [
    "pyproject.toml",
    "uv.lock",
    "poetry.lock",
    "pdm.lock",
    "Pipfile.lock",
];
/// `requirements*.txt`: the prefix and suffix of pip requirement files.
pub(crate) const REQUIREMENTS_FILE_AFFIXES: (&str, &str) = ("requirements", ".txt");

pub(crate) const GIT_PROGRAM: &str = "git";
pub(crate) const INDEX_FILE_ENV: &str = "GIT_INDEX_FILE";
pub(crate) const SHALLOW_TRUE: &str = "true";

pub(crate) const NOT_A_REPOSITORY_CODE: &str = "C480";
pub(crate) const UNKNOWN_REF_CODE: &str = "C481";
pub(crate) const NO_MERGE_BASE_CODE: &str = "C482";
pub(crate) const EXPORT_FAILED_CODE: &str = "C483";
pub(crate) const BASE_REF_UNSET_CODE: &str = "C485";
pub(crate) const DEPTH_HELP: &str = "Fetch enough history to reach the merge base, for example \
                                     `git fetch --unshallow`, or in CI clone with a larger fetch \
                                     depth";
