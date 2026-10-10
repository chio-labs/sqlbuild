//! The stored compile, the facts it is checked against, and one invocation's reuse state.

use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::PathBuf;

use crate::project_snapshot::models::{PathStamp, SnapshotRules};

/// Constants the Python host owns, passed once so both sides agree.
#[derive(Clone, Debug, Default)]
pub struct ReuseRules {
    pub snapshot: SnapshotRules,
    pub tracked_prefixes: Vec<String>,
    pub untracked_names: Vec<String>,
    /// Environment variables that turn reuse off when set to their value.
    pub disabling_variables: Vec<(String, String)>,
    pub config_filenames: Vec<String>,
    pub racy_window_ns: i64,
    pub max_stored_entries: usize,
    pub max_entry_bytes: usize,
    pub missing_environment_value: String,
    pub missing_file_digest: String,
    pub missing_path_mtime_ns: i64,
    pub project_root_path_mtime_ns: i64,
    pub compiled_root: PathBuf,
    /// Directories beside the store directory that older releases kept stored compiles in.
    pub retired_directories: Vec<String>,
}

/// Interpreter and invocation facts only the Python host can read.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct HostIdentity {
    pub invocation_digest: String,
    pub runtime: BTreeMap<String, String>,
    /// `sys.path` in order; stamped natively.
    pub search_path: Vec<String>,
}

/// Where one provider settings class reads values outside the project files.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct SettingsInputs {
    pub case_sensitive: bool,
    pub names: Vec<String>,
    pub prefixes: Vec<String>,
    pub env_files: Vec<String>,
    pub secrets_dirs: Vec<String>,
}

/// One project path recorded before the stored compile ran.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct StoredProjectFile {
    pub stamp: PathStamp,
    pub digest: Option<String>,
    pub racy: bool,
}

/// Every input identity recorded with one stored compile.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct StoredInputs {
    pub invocation_digest: String,
    pub runtime: BTreeMap<String, String>,
    pub search_path: Vec<(String, i64)>,
    pub environment_names: Vec<String>,
    pub environment_digest: String,
    pub modules: Vec<(String, i64, u64)>,
    pub project_files: Vec<StoredProjectFile>,
    pub target_files: Vec<PathStamp>,
    pub target_tree: bool,
    pub settings_inputs: Vec<SettingsInputs>,
    pub settings_digest: String,
}

/// The command output of one stored compile.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct StoredOutput {
    pub stderr_lines: Vec<String>,
    pub exit_code: i64,
    /// Byte span of the `compile_timings` object in `stdout`.
    pub timings_span: Option<(usize, usize)>,
    pub stdout: String,
}

/// Whether one invocation replays, compiles and stores, or bypasses reuse.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ReuseOutcome {
    Hit,
    Miss,
    Bypass,
}

/// One invocation's reuse state, carried from the check to the record.
#[derive(Debug)]
pub struct ReuseAttempt {
    pub outcome: ReuseOutcome,
    pub project_dir: PathBuf,
    pub store_path: PathBuf,
    pub identity: HostIdentity,
    pub search_path: Vec<(String, i64)>,
    pub snapshot: Vec<PathStamp>,
    pub snapshot_ns: i64,
    pub digests: HashMap<String, String>,
    pub restamped: HashSet<String>,
    /// The stored output to replay on a hit.
    pub replay: Option<StoredOutput>,
    /// A stored compile matched but its output could not be replayed.
    pub replay_failed: bool,
    /// Project files the check read to compare or complete content digests.
    pub digested_files: usize,
}

/// What the host asks of one reuse check.
#[derive(Debug)]
pub struct ReuseCheck<'a> {
    pub project_dir: PathBuf,
    pub store_path: PathBuf,
    pub identity: HostIdentity,
    /// The command line turns reuse off (no cache, manifest, profiling or debug).
    pub bypass_requested: bool,
    pub json_output: bool,
    pub rules: &'a ReuseRules,
}

/// What a full compile leaves for the record step.
#[derive(Debug)]
pub struct CompileRecord {
    pub stdout: Option<String>,
    pub stderr_lines: Vec<String>,
    pub exit_code: i64,
    pub compile_cache_enabled: bool,
    pub read_run_id: bool,
    /// Provider settings inputs, or why they cannot be enumerated.
    pub settings: Result<Vec<SettingsInputs>, String>,
    pub template_environment_names: Vec<String>,
    /// Loaded module files and extra module paths, as the host lists them.
    pub module_paths: Vec<String>,
    /// Artifacts the compile wrote (digest) or kept (size and mtime), by absolute path.
    pub artifacts: HashMap<String, RecordedArtifact>,
    pub artifacts_written: bool,
    pub dag_path: Option<String>,
    pub json_output: bool,
}

/// What one compile left at one artifact path.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RecordedArtifact {
    Written { digest: String },
    Kept { size: u64, mtime_ns: i64 },
}

/// What recording did, and how many project files it read for content digests.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RecordResult {
    pub outcome: RecordOutcome,
    pub digested_files: usize,
}

/// Whether recording stored the compile.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RecordOutcome {
    /// Nothing was recorded for this invocation.
    NotAttempted,
    Stored,
    /// The slot was cleared because this compile cannot be reused.
    Removed,
    /// Files changed while the compile ran; the slot was cleared.
    Skipped,
}
