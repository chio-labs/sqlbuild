//! The `--since` base snapshot: resolved from git, compiled in a child interpreter, cached per commit.

use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};
use std::time::Instant;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use sqlbuild_analysis::definition_changes::constants::DEFINITION_SNAPSHOT_FORMAT;
use sqlbuild_analysis::definition_changes::main::definition_digest::definition_digest;
use sqlbuild_analysis::definition_changes::main::definition_snapshot_json::definition_snapshot_json;
use sqlbuild_analysis::definition_changes::main::parse_definition_snapshot::parse_definition_snapshot;
use sqlbuild_analysis::definition_changes::models::DefinitionSnapshot;
use sqlbuild_core::git_revisions::constants::BASE_REF_ALIAS;
use sqlbuild_core::git_revisions::errors::GitRevisionError;
use sqlbuild_core::git_revisions::main::export_git_tree::export_git_tree;
use sqlbuild_core::git_revisions::main::resolve_git_base::resolve_git_base;
use sqlbuild_core::git_revisions::main::resolve_since_reference::resolve_since_reference;
use sqlbuild_core::git_revisions::main::short_commit::short_commit;
use sqlbuild_core::git_revisions::models::GitBase;
use sqlbuild_core::scenario_command::errors::ScenarioCommandError;
use sqlbuild_rules::constants::NATIVE_BUILD_IDENTITY;

use crate::bindings::_helpers::compile_command::runtime_identity::interpreter_values;
use crate::bindings::_helpers::discovery::project_config::configured_git_base_ref;
use crate::bindings::_helpers::planner_identity::json_values::{COMPACT, sorted_dumps};
use crate::bindings::_helpers::scenario_command::setup::{cli_user_error, flush, write};

const CACHE_DIRECTORY: [&str; 2] = ["target", "since"];
const LOCAL_CONFIG_FILE: &str = "sqlbuild_local.toml";
const PROJECT_CONFIG_FILE: &str = "sqlbuild_project.toml";
const BASE_COMPILE_FAILED_CODE: &str = "C484";
const FAILURE_TAIL_LINES: usize = 20;
/// Compiles the exported base tree in a fresh interpreter, apart from the working tree's modules.
const BASE_COMPILE_PROGRAM: &str = "import json, sys\n\
from sqlbuild._native import write_base_definition_snapshot\n\
write_base_definition_snapshot(project_dir=sys.argv[1], output_path=sys.argv[2], \
selected_target=sys.argv[3] or None, cli_vars=json.loads(sys.argv[4]))\n";

/// The base revision and its definition snapshot.
pub(crate) struct BaseComparison {
    pub(crate) base: GitBase,
    pub(crate) snapshot: DefinitionSnapshot,
}

/// The inputs that decide what the base compile produces besides its commit.
pub(crate) struct BaseVariant {
    pub(crate) selected_target: Option<String>,
    /// `--vars` as sorted compact JSON.
    pub(crate) vars_json: String,
}

/// The base variant of a command's `--target` and `--vars`.
pub(crate) fn base_variant(
    selected_target: Option<String>,
    cli_vars: &Bound<'_, PyAny>,
) -> PyResult<BaseVariant> {
    Ok(BaseVariant {
        selected_target,
        vars_json: vars_json(cli_vars)?,
    })
}

fn git_error(py: Python<'_>, error: GitRevisionError) -> PyErr {
    cli_user_error(
        py,
        ScenarioCommandError {
            code: error.code,
            message: error.message,
            help: Some(error.help),
        },
    )
}

fn compile_failed(py: Python<'_>, base: &GitBase, detail: &str) -> PyErr {
    cli_user_error(
        py,
        ScenarioCommandError {
            code: BASE_COMPILE_FAILED_CODE,
            message: format!(
                "Cannot compile the project at merge base {} of '{}' and HEAD:\n{detail}",
                short_commit(&base.merge_base),
                base.reference
            ),
            help: Some(
                "--since compares with the project as it was at the merge base, so that \
                 revision must compile. Compare with a later ref whose project compiles, or run \
                 without --since to run everything"
                    .to_owned(),
            ),
        },
    )
}

fn io_failed(py: Python<'_>, base: &GitBase, error: &std::io::Error) -> PyErr {
    compile_failed(py, base, &error.to_string())
}

/// The last lines of a failed base compile's output.
fn failure_tail(output: &Output) -> String {
    let text: String = format!(
        "{}{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    let lines: Vec<&str> = text
        .lines()
        .filter(|line| !line.trim().is_empty())
        .collect();
    lines[lines.len().saturating_sub(FAILURE_TAIL_LINES)..].join("\n")
}

fn vars_json(cli_vars: &Bound<'_, PyAny>) -> PyResult<String> {
    if cli_vars.is_none() {
        return Ok("{}".to_owned());
    }
    sorted_dumps(cli_vars, COMPACT, true)
}

/// Run the base compile of `tree` into `output` in a separate interpreter.
fn compile_base_tree(
    py: Python<'_>,
    base: &GitBase,
    (tree, output): (&Path, &Path),
    (selected_target, vars): (Option<&str>, &str),
) -> PyResult<()> {
    let [_, executable, _, _] = interpreter_values(py)?;
    let finished: std::io::Result<Output> = py.detach(|| {
        Command::new(&executable)
            .arg("-c")
            .arg(BASE_COMPILE_PROGRAM)
            .arg(tree)
            .arg(output)
            .arg(selected_target.unwrap_or_default())
            .arg(vars)
            .current_dir(tree)
            .stdin(Stdio::null())
            .output()
    });
    let finished: Output = finished.map_err(|error| io_failed(py, base, &error))?;
    if finished.status.success() && output.is_file() {
        return Ok(());
    }
    Err(compile_failed(py, base, &failure_tail(&finished)))
}

/// Export the base tree, carry over the untracked local config, and compile it.
fn compiled_base_snapshot(
    py: Python<'_>,
    (base, project_dir, work): (&GitBase, &Path, &Path),
    (selected_target, vars): (Option<&str>, &str),
) -> PyResult<DefinitionSnapshot> {
    let tree: PathBuf = work.join("project");
    let exported: bool = export_git_tree(base, &tree).map_err(|error| git_error(py, error))?;
    if !exported || !tree.join(PROJECT_CONFIG_FILE).is_file() {
        return Ok(DefinitionSnapshot {
            format: DEFINITION_SNAPSHOT_FORMAT,
            ..DefinitionSnapshot::default()
        });
    }
    let local: PathBuf = project_dir.join(LOCAL_CONFIG_FILE);
    if local.is_file() && !tree.join(LOCAL_CONFIG_FILE).exists() {
        std::fs::copy(&local, tree.join(LOCAL_CONFIG_FILE))
            .map_err(|error| io_failed(py, base, &error))?;
    }
    let output: PathBuf = work.join("definitions.json");
    compile_base_tree(py, base, (&tree, &output), (selected_target, vars))?;
    let text: String =
        std::fs::read_to_string(&output).map_err(|error| io_failed(py, base, &error))?;
    parse_definition_snapshot(&text)
        .ok_or_else(|| compile_failed(py, base, "the base compile wrote an unreadable snapshot"))
}

/// Resolve `since` to its merge base and load, or compile and cache, the base snapshot.
pub(crate) fn base_comparison<'py>(
    (stream, project_dir): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    since: &str,
    variant: &BaseVariant,
) -> PyResult<BaseComparison> {
    let py: Python<'py> = stream.py();
    let directory: PathBuf = project_dir.extract()?;
    let configured: Option<String> = if since.trim() == BASE_REF_ALIAS {
        configured_git_base_ref(project_dir)?
    } else {
        None
    };
    let reference: String = resolve_since_reference(since, configured.as_deref())
        .map_err(|error| git_error(py, error))?;
    let base: GitBase = py
        .detach(|| resolve_git_base(&directory, &reference))
        .map_err(|error| git_error(py, error))?;
    let short: &str = short_commit(&base.merge_base);
    write(
        stream,
        &format!("Comparing with {reference} (merge base {short})\n"),
    )?;
    let vars: &str = &variant.vars_json;
    let target: Option<&str> = variant.selected_target.as_deref();
    let local_config: String =
        std::fs::read_to_string(directory.join(LOCAL_CONFIG_FILE)).unwrap_or_default();
    let key: String = definition_digest(&[
        NATIVE_BUILD_IDENTITY,
        target.unwrap_or_default(),
        vars,
        &local_config,
    ]);
    let cache_dir: PathBuf = CACHE_DIRECTORY
        .iter()
        .fold(directory.clone(), |path, part| path.join(part));
    let cached: PathBuf = cache_dir.join(format!("{}-{}.json", base.merge_base, &key[..16]));
    let stored: Option<DefinitionSnapshot> = match std::fs::read_to_string(&cached) {
        Ok(text) => parse_definition_snapshot(&text),
        Err(_) => None,
    };
    if let Some(snapshot) = stored {
        write(stream, &format!("Using cached base revision {short}\n"))?;
        flush(stream)?;
        return Ok(BaseComparison { base, snapshot });
    }
    write(stream, &format!("Compiling base revision {short}...\n"))?;
    flush(stream)?;
    let started: Instant = Instant::now();
    let work: PathBuf = cache_dir.join(format!("work-{}-{}", short, std::process::id()));
    let _ = std::fs::remove_dir_all(&work);
    std::fs::create_dir_all(&work).map_err(|error| io_failed(py, &base, &error))?;
    let compiled: PyResult<DefinitionSnapshot> =
        compiled_base_snapshot(py, (&base, &directory, &work), (target, vars));
    let _ = std::fs::remove_dir_all(&work);
    let snapshot: DefinitionSnapshot = compiled?;
    let staged: PathBuf = cached.with_extension(format!("{}.tmp", std::process::id()));
    if let Ok(()) = std::fs::write(&staged, definition_snapshot_json(&snapshot)) {
        let _ = std::fs::rename(&staged, &cached);
    }
    write(
        stream,
        &format!(
            "Compiled base revision {short} ({:.2}s)\n",
            started.elapsed().as_secs_f64()
        ),
    )?;
    flush(stream)?;
    Ok(BaseComparison { base, snapshot })
}
