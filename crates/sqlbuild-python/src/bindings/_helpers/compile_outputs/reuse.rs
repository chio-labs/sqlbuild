//! Whole-project compile reuse on the shared native store, driven by the Python host's facts.

use std::collections::{BTreeMap, HashMap};
use std::ffi::{OsStr, OsString};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{FromPyObject, pyclass, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_cache::digest::main::bytes_digest::bytes_digest;
use sqlbuild_cache::digest::main::hex_digest::hex_digest;
use sqlbuild_cache::project_reuse::constants::{NATIVE_DIGEST_PREFIX, REUSE_STORE_SUFFIX};
use sqlbuild_cache::project_reuse::main::check_reuse::check_reuse;
use sqlbuild_cache::project_reuse::main::pending_digest_bytes::pending_digest_bytes;
use sqlbuild_cache::project_reuse::main::record_reuse::record_reuse;
use sqlbuild_cache::project_reuse::main::replay_stdout::replay_stdout;
use sqlbuild_cache::project_reuse::models::{
    CompileRecord, HostIdentity, RecordOutcome, RecordResult, RecordedArtifact, ReuseAttempt,
    ReuseCheck, ReuseOutcome, ReuseRules, SettingsInputs, StoredOutput,
};
use sqlbuild_cache::project_snapshot::main::path_text::path_text;
use sqlbuild_cache::project_snapshot::models::SnapshotRules;

use crate::bindings::_helpers::boundary::panics::compiler_guard;

type SettingsRow = (bool, Vec<String>, Vec<String>, Vec<String>, Vec<String>);
type ReplayRow = (String, Vec<String>, i64);
/// A written artifact's digest, or a kept artifact's size and mtime.
type ArtifactRow = (Option<String>, Option<u64>, Option<i64>);

/// The host constants the walk, environment and store checks use.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct ReuseRulesPy {
    excluded: Vec<String>,
    excluded_root: Vec<String>,
    presence_suffixes: Vec<String>,
    output_files: Vec<(u64, u64)>,
    tracked_prefixes: Vec<String>,
    untracked_names: Vec<String>,
    disabling_variables: Vec<(String, String)>,
    config_filenames: Vec<String>,
    racy_window_ns: i64,
    max_stored_entries: usize,
    max_entry_bytes: usize,
    missing_environment_value: String,
    missing_file_digest: String,
    missing_path_mtime_ns: i64,
    project_root_path_mtime_ns: i64,
    compiled_root: PathBuf,
    retired_directories: Vec<String>,
}

impl From<ReuseRulesPy> for ReuseRules {
    fn from(rules: ReuseRulesPy) -> Self {
        Self {
            snapshot: SnapshotRules {
                excluded: rules.excluded,
                excluded_root: rules.excluded_root,
                presence_suffixes: rules.presence_suffixes,
                output_files: rules.output_files,
            },
            tracked_prefixes: rules.tracked_prefixes,
            untracked_names: rules.untracked_names,
            disabling_variables: rules.disabling_variables,
            config_filenames: rules.config_filenames,
            racy_window_ns: rules.racy_window_ns,
            max_stored_entries: rules.max_stored_entries,
            max_entry_bytes: rules.max_entry_bytes,
            missing_environment_value: rules.missing_environment_value,
            missing_file_digest: rules.missing_file_digest,
            missing_path_mtime_ns: rules.missing_path_mtime_ns,
            project_root_path_mtime_ns: rules.project_root_path_mtime_ns,
            compiled_root: rules.compiled_root,
            retired_directories: rules.retired_directories,
        }
    }
}

/// One reuse check: where the project and its store slot are, and the host's identity facts.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct ReuseCheckPy {
    project_dir: PathBuf,
    store_directory: PathBuf,
    selected_target: Option<OsString>,
    invocation: Vec<u8>,
    runtime: BTreeMap<String, OsString>,
    search_path: Vec<OsString>,
    bypass_requested: bool,
    json_output: bool,
    rules: ReuseRulesPy,
}

/// What a full compile leaves for recording; `artifacts` maps a path to `(digest, size, mtime)`.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct CompileRecordPy {
    stdout: Option<String>,
    stderr_lines: Vec<String>,
    exit_code: i64,
    compile_cache_enabled: bool,
    read_run_id: bool,
    settings_inputs: Option<Vec<SettingsRow>>,
    template_environment_names: Vec<String>,
    module_paths: Vec<OsString>,
    artifacts: HashMap<String, ArtifactRow>,
    artifacts_written: bool,
    dag_path: Option<String>,
    json_output: bool,
    rules: ReuseRulesPy,
}

/// One invocation's native reuse state, from the check to the record.
#[pyclass(module = "sqlbuild._native", frozen)]
struct NativeReuseAttempt {
    attempt: Mutex<ReuseAttempt>,
}

fn poisoned<T>(_: T) -> pyo3::PyErr {
    PyValueError::new_err("compile reuse attempt is poisoned")
}

#[pymethods]
impl NativeReuseAttempt {
    /// `"hit"`, `"miss"` or `"bypass"`.
    fn outcome(&self) -> PyResult<&'static str> {
        Ok(match self.attempt.lock().map_err(poisoned)?.outcome {
            ReuseOutcome::Hit => "hit",
            ReuseOutcome::Miss => "miss",
            ReuseOutcome::Bypass => "bypass",
        })
    }

    /// The store file holding this invocation's slot.
    fn store_path(&self) -> PyResult<String> {
        let attempt = self.attempt.lock().map_err(poisoned)?;
        Ok(attempt.store_path.to_string_lossy().into_owned())
    }

    /// Whether a stored compile matched but could not be replayed.
    fn replay_failed(&self) -> PyResult<bool> {
        Ok(self.attempt.lock().map_err(poisoned)?.replay_failed)
    }

    /// How many project paths the check stamped.
    fn snapshot_paths(&self) -> PyResult<usize> {
        Ok(self.attempt.lock().map_err(poisoned)?.snapshot.len())
    }

    /// Bytes recording would hash for files whose stamp moved.
    fn pending_digest_bytes(&self) -> PyResult<u64> {
        let attempt = self.attempt.lock().map_err(poisoned)?;
        Ok(pending_digest_bytes(&attempt))
    }

    /// On a hit, the stored report with these timings plus its stderr lines and exit code.
    fn replay(&self, timings: Vec<(String, i64)>) -> PyResult<Option<ReplayRow>> {
        let attempt = self.attempt.lock().map_err(poisoned)?;
        let Some(output) = attempt.replay.as_ref() else {
            return Ok(None);
        };
        let output: &StoredOutput = output;
        Ok(replay_stdout(output, &timings)
            .map(|stdout| (stdout, output.stderr_lines.clone(), output.exit_code)))
    }

    /// How many project files the check read for content digests.
    fn digested_files(&self) -> PyResult<usize> {
        Ok(self.attempt.lock().map_err(poisoned)?.digested_files)
    }

    /// Store this compile or clear the slot; a failure clears the slot and raises `OSError`.
    fn record(&self, py: Python<'_>, record: CompileRecordPy) -> PyResult<(&'static str, usize)> {
        compiler_guard(|| {
            let rules: ReuseRules = record.rules.into();
            let compile: CompileRecord = CompileRecord {
                stdout: record.stdout,
                stderr_lines: record.stderr_lines,
                exit_code: record.exit_code,
                compile_cache_enabled: record.compile_cache_enabled,
                read_run_id: record.read_run_id,
                settings: record
                    .settings_inputs
                    .map(|rows| rows.into_iter().map(settings_inputs).collect())
                    .ok_or_else(String::new),
                template_environment_names: record.template_environment_names,
                module_paths: texts(&record.module_paths),
                artifacts: record
                    .artifacts
                    .into_iter()
                    .map(|(path, artifact)| (path, recorded_artifact(artifact)))
                    .collect(),
                artifacts_written: record.artifacts_written,
                dag_path: record.dag_path,
                json_output: record.json_output,
            };
            let attempt = self.attempt.lock().map_err(poisoned)?;
            let result: RecordResult = py
                .detach(|| record_reuse(&attempt, &compile, &rules))
                .map_err(|error| pyo3::exceptions::PyOSError::new_err(error.message))?;
            let outcome: &'static str = match result.outcome {
                RecordOutcome::NotAttempted => "not_attempted",
                RecordOutcome::Stored => "stored",
                RecordOutcome::Removed => "removed",
                RecordOutcome::Skipped => "skipped",
            };
            Ok((outcome, result.digested_files))
        })
    }
}

fn settings_inputs(row: SettingsRow) -> SettingsInputs {
    let (case_sensitive, names, prefixes, env_files, secrets_dirs) = row;
    SettingsInputs {
        case_sensitive,
        names,
        prefixes,
        env_files,
        secrets_dirs,
    }
}

fn recorded_artifact(artifact: ArtifactRow) -> RecordedArtifact {
    match artifact {
        (Some(digest), _, _) => RecordedArtifact::Written { digest },
        (None, size, mtime_ns) => RecordedArtifact::Kept {
            size: size.unwrap_or_default(),
            mtime_ns: mtime_ns.unwrap_or_default(),
        },
    }
}

/// Check the stored compile for this invocation, replaying it on a hit.
#[pyfunction]
fn check_compile_reuse(py: Python<'_>, check: ReuseCheckPy) -> PyResult<NativeReuseAttempt> {
    compiler_guard(|| {
        let rules: ReuseRules = check.rules.into();
        let request: ReuseCheck<'_> = ReuseCheck {
            project_dir: check.project_dir,
            store_path: store_slot(&check.store_directory, check.selected_target.as_deref()),
            identity: HostIdentity {
                invocation_digest: native_digest(&check.invocation),
                runtime: check
                    .runtime
                    .iter()
                    .map(|(name, value)| (name.clone(), path_text(value)))
                    .collect(),
                search_path: texts(&check.search_path),
            },
            bypass_requested: check.bypass_requested,
            json_output: check.json_output,
            rules: &rules,
        };
        let attempt: ReuseAttempt = py.detach(|| check_reuse(request));
        Ok(NativeReuseAttempt {
            attempt: Mutex::new(attempt),
        })
    })
}

/// The native content digest of artifact bytes, as reuse verifies written artifacts.
#[pyfunction]
fn artifact_digest(contents: &[u8]) -> String {
    native_digest(contents)
}

fn native_digest(contents: &[u8]) -> String {
    format!(
        "{NATIVE_DIGEST_PREFIX}{}",
        hex_digest(&bytes_digest(contents))
    )
}

/// The one store file kept for the selected target.
fn store_slot(directory: &Path, selected_target: Option<&OsStr>) -> PathBuf {
    let label: String = selected_target.map_or_else(String::new, |target| {
        format!("target:{}", path_text(target))
    });
    directory.join(format!(
        "{}.{REUSE_STORE_SUFFIX}",
        hex_digest(&bytes_digest(label.as_bytes()))
    ))
}

/// Host strings that may carry undecodable bytes, as exact text.
fn texts(values: &[OsString]) -> Vec<String> {
    values.iter().map(|value| path_text(value)).collect()
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeReuseAttempt>()?;
    module.add_function(wrap_pyfunction!(check_compile_reuse, module)?)?;
    module.add_function(wrap_pyfunction!(artifact_digest, module)?)
}
