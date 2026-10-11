//! The launch record the Python CLI writes after a reusable compile.

use std::collections::BTreeMap;

use serde::Deserialize;

/// The reuse constants the Python host owns, as `reuse_rules()` returns them.
#[derive(Clone, Debug, Deserialize, PartialEq, Eq)]
pub struct LaunchRules {
    pub excluded: Vec<String>,
    pub excluded_root: Vec<String>,
    pub presence_suffixes: Vec<String>,
    pub tracked_prefixes: Vec<String>,
    pub untracked_names: Vec<String>,
    pub disabling_variables: Vec<(String, String)>,
    pub config_filenames: Vec<String>,
    pub racy_window_ns: i64,
    pub max_stored_entries: usize,
    pub max_entry_bytes: usize,
    pub missing_environment_value: String,
    pub missing_file_digest: String,
    pub missing_path_mtime_ns: i64,
    pub project_root_path_mtime_ns: i64,
    pub compiled_root: String,
    pub retired_directories: Vec<String>,
}

/// Where the Python CLI captured this invocation's compute logs.
#[derive(Clone, Debug, Deserialize, PartialEq, Eq)]
pub struct LaunchCapture {
    pub root: String,
    pub command: String,
    pub project_dir: String,
    pub target: Option<String>,
}

/// The `compile_timings` names a JSON replay reports.
#[derive(Clone, Debug, Deserialize, PartialEq, Eq)]
pub struct LaunchTimings {
    pub hit: String,
    pub miss: String,
    pub bypass: String,
    pub check: String,
    pub total: String,
}

/// Everything a reuse hit needs that only the Python process could know.
#[derive(Clone, Debug, Deserialize, PartialEq, Eq)]
pub struct LaunchRecord {
    pub format: i64,
    pub key: String,
    pub project_dir: String,
    pub store_path: String,
    pub invocation_digest: String,
    pub runtime: BTreeMap<String, String>,
    pub search_path: Vec<String>,
    pub startup_inputs: Vec<(String, Option<i64>, Option<u64>)>,
    pub json_output: bool,
    pub rules: LaunchRules,
    pub capture: Option<LaunchCapture>,
    /// The hit notice before and after its `{seconds:.1f}` field.
    pub hit_message: (String, String),
    pub timings: LaunchTimings,
}

/// One served invocation: what was written and the exit code.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ServedInvocation {
    pub stdout: String,
    pub stderr: String,
    pub exit_code: i64,
}
