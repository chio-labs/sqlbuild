//! Check whether a compile can replay the stored result, replay it on a hit and leave a launch record.

use std::path::PathBuf;

use pyo3::exceptions::PyOSError;
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyList, PyString};
use pyo3::{IntoPyObjectExt, pyfunction, wrap_pyfunction};
use sqlbuild_cli::replay::main::write_launch_record::write_launch_record as write_record_file;
use sqlbuild_core::command_output::constants::INVOCATION_CONTEXT_ENV;

use sqlbuild_cli::replay::constants::{LAUNCH_RECORD_DIRECTORY, LAUNCH_RECORD_FORMAT};

use crate::bindings::_helpers::cli::launch_state::launch_record_path;
use crate::bindings::_helpers::compile_command::constants::{
    COMPILE_CACHE_DISABLE_ENV_VAR, COMPILE_CACHE_DISABLE_VALUE, COMPILE_COMMAND_NAME,
    COMPILED_DIRECTORY_NAME, COMPUTE_LOG_DIRECTORY_NAME, EXCLUDED_DIRECTORIES,
    EXCLUDED_ROOT_ATTRIBUTE, EXCLUDED_ROOT_DIRECTORIES, MILLISECONDS_PER_SECOND,
    MISSING_ENVIRONMENT_VALUE, MISSING_FILE_DIGEST, MISSING_PATH_MTIME_NS,
    NATIVE_REUSE_DIRECTORY_NAME, PRESENCE_ONLY_FILE_SUFFIXES, PROJECT_CONFIG_FILENAMES,
    PROJECT_ROOT_PATH_MTIME_NS, RACY_WINDOW_ATTRIBUTE, RACY_WINDOW_NS,
    RETIRED_REUSE_DIRECTORY_NAME, REUSE_BYPASS_TIMING, REUSE_CHECK_TIMING, REUSE_DISABLE_ENV_VAR,
    REUSE_DISABLE_VALUE, REUSE_HIT_MESSAGE, REUSE_HIT_TIMING, REUSE_LOGGER_NAME,
    REUSE_MAX_ENTRY_BYTES, REUSE_MAX_STORED_ENTRIES, REUSE_MISS_TIMING, TARGET_DIRECTORY_NAME,
    TOTAL_TIMING, TRACKED_ENVIRONMENT_PREFIXES, UNTRACKED_ENVIRONMENT_NAMES,
};
use crate::bindings::_helpers::compile_command::models::CompileReuseAttempt;
use crate::bindings::_helpers::compile_driver::phases::{elapsed_ms, monotonic};
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, keywords};
use crate::bindings::_helpers::compile_outputs::json_report::plain_json;
use crate::bindings::_helpers::frontier::cache_directory::cache_directory;
use crate::bindings::_helpers::presentation_text::terminal::stdout_supports_color;

const NATIVE_MODULE: &str = "sqlbuild._native";
const REUSE_REQUEST: (&str, &str) = ("sqlbuild.cli.compile_reuse.models", "CompileReuseRequest");
const RUNTIME_IDENTITY_MODULE: &str = "sqlbuild.cli.compile_reuse._helpers.runtime_identity";
const STARTUP_INPUTS_MODULE: &str = "sqlbuild.cli.compile_reuse._helpers.startup_inputs";
const COMPUTE_LOG_TEE_MODULE: &str = "sqlbuild.runtime.compute_logs.classes.text_tee";
const HIT: &str = "hit";
const CHECKED_HIT: &str = "hit";
const CHECKED_BYPASS: &str = "bypass";
const MISS: &str = "miss";
const BYPASS: &str = "bypass";

fn listed<'py>(value: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    Ok(PyList::new(value.py(), value.try_iter()?.collect::<PyResult<Vec<_>>>()?)?.into_any())
}

fn reuse_logger(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    imported(py, "logging", "getLogger")?.call1((REUSE_LOGGER_NAME,))
}

/// The reuse constants the native check, the stored compile and the launch record share.
pub(crate) fn reuse_rules(py: Python<'_>, with_output_files: bool) -> PyResult<Bound<'_, PyDict>> {
    let rules: Bound<'_, PyDict> = PyDict::new(py);
    rules.set_item("excluded", PyList::new(py, EXCLUDED_DIRECTORIES)?)?;
    rules.set_item(
        "excluded_root",
        imported(py, "builtins", "sorted")?.call1((imported(
            py,
            NATIVE_MODULE,
            EXCLUDED_ROOT_ATTRIBUTE,
        )?,))?,
    )?;
    rules.set_item(
        "presence_suffixes",
        PyList::new(py, PRESENCE_ONLY_FILE_SUFFIXES)?,
    )?;
    let output_files: Bound<'_, PyAny> =
        imported(py, RUNTIME_IDENTITY_MODULE, "redirected_output_files")?.call0()?;
    if with_output_files {
        rules.set_item("output_files", output_files)?;
    }
    rules.set_item(
        "tracked_prefixes",
        PyList::new(py, TRACKED_ENVIRONMENT_PREFIXES)?,
    )?;
    rules.set_item(
        "untracked_names",
        PyList::new(py, UNTRACKED_ENVIRONMENT_NAMES)?,
    )?;
    rules.set_item(
        "disabling_variables",
        PyList::new(
            py,
            [
                (
                    COMPILE_CACHE_DISABLE_ENV_VAR.into_bound_py_any(py)?,
                    COMPILE_CACHE_DISABLE_VALUE.into_bound_py_any(py)?,
                ),
                (
                    REUSE_DISABLE_ENV_VAR.into_bound_py_any(py)?,
                    REUSE_DISABLE_VALUE.into_bound_py_any(py)?,
                ),
            ],
        )?,
    )?;
    rules.set_item(
        "config_filenames",
        PyList::new(py, PROJECT_CONFIG_FILENAMES)?,
    )?;
    for (key, value) in [
        ("max_stored_entries", REUSE_MAX_STORED_ENTRIES),
        ("max_entry_bytes", REUSE_MAX_ENTRY_BYTES),
        ("missing_path_mtime_ns", MISSING_PATH_MTIME_NS),
        ("project_root_path_mtime_ns", PROJECT_ROOT_PATH_MTIME_NS),
    ] {
        rules.set_item(key, value)?;
    }
    rules.set_item(
        "racy_window_ns",
        imported(py, NATIVE_MODULE, RACY_WINDOW_ATTRIBUTE)?,
    )?;
    rules.set_item("missing_environment_value", MISSING_ENVIRONMENT_VALUE)?;
    rules.set_item("missing_file_digest", MISSING_FILE_DIGEST)?;
    rules.set_item(
        "compiled_root",
        format!(
            "{TARGET_DIRECTORY_NAME}{}{COMPILED_DIRECTORY_NAME}",
            std::path::MAIN_SEPARATOR
        ),
    )?;
    rules.set_item(
        "retired_directories",
        PyList::new(py, [RETIRED_REUSE_DIRECTORY_NAME])?,
    )?;
    Ok(rules)
}

/// The launch record `sqb` replays this reusable compile from, as a JSON object.
fn launch_payload<'py>(
    attempt: &Bound<'py, PyAny>,
    native: &Bound<'py, PyAny>,
    key: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = attempt.py();
    let (invocation_digest, runtime, search_path): (
        Bound<'py, PyAny>,
        Bound<'py, PyAny>,
        Bound<'py, PyAny>,
    ) = native.call_method0("launch_identity")?.extract()?;
    let project_dir: Bound<'py, PyAny> = attempt.getattr("project_dir")?;
    let resolved: Bound<'py, PyAny> = project_dir.call_method0("resolve")?;
    let capture: Bound<'py, PyAny> = if py
        .import("sys")?
        .getattr("stdout")?
        .is_instance(&imported(py, COMPUTE_LOG_TEE_MODULE, "TextComputeLogTee")?)?
    {
        let logs: Bound<'py, PyAny> = resolved
            .call_method1("__truediv__", (COMPUTE_LOG_DIRECTORY_NAME,))?
            .call_method0("resolve")?;
        let capture: Bound<'py, PyDict> = PyDict::new(py);
        capture.set_item("root", logs.str()?)?;
        capture.set_item("command", COMPILE_COMMAND_NAME)?;
        capture.set_item("project_dir", resolved.str()?)?;
        capture.set_item("target", attempt.getattr("selected_target")?)?;
        capture.into_any()
    } else {
        py.None().into_bound(py)
    };
    let timings: Bound<'py, PyDict> = PyDict::new(py);
    for (key, name) in [
        ("hit", REUSE_HIT_TIMING),
        ("miss", REUSE_MISS_TIMING),
        ("bypass", REUSE_BYPASS_TIMING),
        ("check", REUSE_CHECK_TIMING),
        ("total", TOTAL_TIMING),
    ] {
        timings.set_item(key, name)?;
    }
    let payload: Bound<'py, PyDict> = PyDict::new(py);
    payload.set_item("format", LAUNCH_RECORD_FORMAT)?;
    payload.set_item("key", key)?;
    payload.set_item("project_dir", project_dir.str()?)?;
    payload.set_item("store_path", native.call_method0("store_path")?)?;
    payload.set_item("invocation_digest", invocation_digest)?;
    payload.set_item("runtime", runtime)?;
    payload.set_item("search_path", search_path)?;
    payload.set_item(
        "startup_inputs",
        imported(py, STARTUP_INPUTS_MODULE, "startup_inputs")?.call0()?,
    )?;
    payload.set_item("json_output", attempt.getattr("json_output")?)?;
    payload.set_item("rules", reuse_rules(py, false)?)?;
    payload.set_item("capture", capture)?;
    payload.set_item("hit_message", PyList::new(py, REUSE_HIT_MESSAGE)?)?;
    payload.set_item("timings", timings)?;
    Ok(payload)
}

fn write_record(
    attempt: &Bound<'_, PyAny>,
    native: &Bound<'_, PyAny>,
    path: &Bound<'_, PyAny>,
) -> PyResult<()> {
    let payload: Bound<'_, PyDict> = launch_payload(attempt, native, path.getattr("stem")?)?;
    let text: String = plain_json(payload.as_any())?;
    let path: PathBuf = path.extract()?;
    write_record_file(&path, &text).map_err(PyErr::from)
}

/// Record this reusable compile for `sqb` when nothing it cannot replay took part.
pub(crate) fn write_launch_record(attempt: &Bound<'_, PyAny>) -> PyResult<()> {
    let py: Python<'_> = attempt.py();
    let path: Bound<'_, PyAny> = launch_record_path(py)?;
    let native: Bound<'_, PyAny> = attempt.getattr("native")?;
    if path.is_none() || native.is_none() {
        return Ok(());
    }
    let environment: Bound<'_, PyAny> = imported(py, "os", "environ")?;
    if environment.contains(INVOCATION_CONTEXT_ENV)? {
        return Ok(());
    }
    let mut directory: Bound<'_, PyAny> = attempt.getattr("project_dir")?;
    for part in LAUNCH_RECORD_DIRECTORY {
        directory = directory.call_method1("__truediv__", (part,))?;
    }
    if path
        .getattr("parent")?
        .call_method0("resolve")?
        .ne(directory.call_method0("resolve")?)?
    {
        return Ok(());
    }
    match write_record(attempt, &native, &path) {
        Err(error) if error.is_instance_of::<PyOSError>(py) => {
            reuse_logger(py)?.call_method(
                "debug",
                ("Compile reuse did not leave a launch record",),
                Some(&keywords(
                    py,
                    &[("exc_info", error.value(py).clone().into_any())],
                )?),
            )?;
            Ok(())
        }
        written => written,
    }
}

fn outcome<'py>(py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyAny>> {
    name.into_bound_py_any(py)
}

/// A `CompileReuseAttempt` with `fields`.
fn reuse_attempt<'py>(
    py: Python<'py>,
    fields: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    call_with(py.get_type::<CompileReuseAttempt>().as_any(), fields)
}

/// The native reuse check request for this invocation.
fn reuse_check<'py>(
    request: &Bound<'py, PyAny>,
    project_dir: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = request.py();
    let flag = |name: &str| -> PyResult<bool> { request.getattr(name)?.is_truthy() };
    let use_color: bool = !flag("no_color")? && stdout_supports_color(py)?;
    let check: Bound<'py, PyDict> = PyDict::new(py);
    check.set_item("project_dir", project_dir)?;
    check.set_item(
        "store_directory",
        cache_directory(&imported(py, "pathlib", "Path")?.call1((project_dir,))?)?
            .call_method1("__truediv__", (NATIVE_REUSE_DIRECTORY_NAME,))?,
    )?;
    check.set_item("selected_target", request.getattr("selected_target")?)?;
    check.set_item(
        "invocation",
        call_with(
            &imported(py, RUNTIME_IDENTITY_MODULE, "invocation_identity")?,
            &[
                ("request", request.clone()),
                ("project_dir", project_dir.clone()),
                ("use_color", use_color.into_bound_py_any(py)?),
            ],
        )?,
    )?;
    check.set_item(
        "runtime",
        imported(py, RUNTIME_IDENTITY_MODULE, "runtime_identity")?.call0()?,
    )?;
    check.set_item("search_path", listed(py.import("sys")?.getattr("path")?)?)?;
    check.set_item(
        "bypass_requested",
        flag("no_cache")? || flag("manifest")? || flag("profiling")? || flag("debug")?,
    )?;
    check.set_item("json_output", request.getattr("json_output")?)?;
    check.set_item("rules", reuse_rules(py, true)?)?;
    Ok(check)
}

/// `print(text, file=sys.stderr)`.
fn print_stderr(py: Python<'_>, text: &Bound<'_, PyAny>) -> PyResult<()> {
    py.import("builtins")?.getattr("print")?.call(
        (text,),
        Some(&keywords(
            py,
            &[("file", py.import("sys")?.getattr("stderr")?)],
        )?),
    )?;
    Ok(())
}

/// `fields` with each override replacing the field of the same name, as `dataclasses.replace`.
fn overridden<'py>(
    mut fields: Vec<(&'static str, Bound<'py, PyAny>)>,
    overrides: Vec<(&'static str, Bound<'py, PyAny>)>,
) -> Vec<(&'static str, Bound<'py, PyAny>)> {
    for (name, value) in overrides {
        match fields.iter_mut().find(|field| field.0 == name) {
            Some(field) => field.1 = value,
            None => fields.push((name, value)),
        }
    }
    fields
}

/// Replay the stored compile on a hit; the missed attempt when it cannot be replayed.
fn replayed<'py>(
    native: &Bound<'py, PyAny>,
    missed: Vec<(&'static str, Bound<'py, PyAny>)>,
    (started, json_output): (f64, bool),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = native.py();
    let check_ms: i64 = elapsed_ms(py, started)?;
    let timings: Vec<(&str, i64)> = vec![
        (REUSE_HIT_TIMING, 1),
        (REUSE_MISS_TIMING, 0),
        (REUSE_BYPASS_TIMING, 0),
        (REUSE_CHECK_TIMING, check_ms),
        (TOTAL_TIMING, elapsed_ms(py, started)?),
    ];
    let rows: Bound<'py, PyList> = if json_output {
        PyList::new(py, timings)?
    } else {
        PyList::empty(py)
    };
    let replay: Bound<'py, PyAny> = native.call_method1("replay", (rows,))?;
    if replay.is_none() {
        return reuse_attempt(
            py,
            &overridden(missed, vec![("check_ms", 0_i64.into_bound_py_any(py)?)]),
        );
    }
    let (stdout, stderr_lines, exit_code): (
        Bound<'py, PyString>,
        Bound<'py, PyAny>,
        Bound<'py, PyAny>,
    ) = replay.extract()?;
    let [prefix, suffix] = REUSE_HIT_MESSAGE;
    let seconds: f64 = check_ms as f64 / MILLISECONDS_PER_SECOND;
    print_stderr(
        py,
        &format!("{prefix}{seconds:.1}{suffix}").into_bound_py_any(py)?,
    )?;
    for line in stderr_lines.try_iter()? {
        print_stderr(py, &line?)?;
    }
    let output: Bound<'py, PyAny> = py.import("sys")?.getattr("stdout")?;
    output.call_method1("write", (stdout,))?;
    output.call_method0("flush")?;
    reuse_attempt(
        py,
        &overridden(
            missed,
            vec![
                ("outcome", outcome(py, HIT)?),
                ("check_ms", check_ms.into_bound_py_any(py)?),
                ("exit_code", exit_code),
            ],
        ),
    )
}

/// Replay the stored compile when every input matches, otherwise prepare to store one.
#[pyfunction]
#[pyo3(signature = (*, request))]
fn attempt_compile_reuse<'py>(request: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let started: f64 = monotonic(py)?;
    let requested: Bound<'py, PyAny> = request.getattr("project_dir")?;
    let project_dir: Bound<'py, PyAny> =
        imported(py, "os.path", "abspath")?.call1((if requested.is_none() {
            imported(py, "os", "getcwd")?.call0()?
        } else {
            requested
        },))?;
    let native: Bound<'py, PyAny> = imported(py, NATIVE_MODULE, "check_compile_reuse")?
        .call1((reuse_check(request, &project_dir)?,))?;
    let checked: String = native.call_method0("outcome")?.extract()?;
    let json_output: Bound<'py, PyAny> = request.getattr("json_output")?;
    let mut base: Vec<(&'static str, Bound<'py, PyAny>)> = vec![
        (
            "project_dir",
            imported(py, "pathlib", "Path")?.call1((&project_dir,))?,
        ),
        ("started", started.into_bound_py_any(py)?),
        ("selected_target", request.getattr("selected_target")?),
        ("json_output", json_output.clone()),
    ];
    if checked == CHECKED_BYPASS {
        base.push(("outcome", outcome(py, BYPASS)?));
        return reuse_attempt(py, &base);
    }
    reuse_logger(py)?.call_method1(
        "debug",
        (
            "Compile reuse check digested %d project files",
            native.call_method0("digested_files")?,
        ),
    )?;
    let check_ms: i64 = if native.call_method0("replay_failed")?.is_truthy()? {
        0
    } else {
        elapsed_ms(py, started)?
    };
    base.extend([
        ("outcome", outcome(py, MISS)?),
        (
            "entry_path",
            imported(py, "pathlib", "Path")?.call1((native.call_method0("store_path")?,))?,
        ),
        ("native", native.clone()),
        ("check_ms", check_ms.into_bound_py_any(py)?),
    ]);
    if checked != CHECKED_HIT {
        return reuse_attempt(py, &base);
    }
    let attempt: Bound<'py, PyAny> = replayed(&native, base, (started, json_output.is_truthy()?))?;
    if attempt.getattr("outcome")?.eq(outcome(py, HIT)?)? {
        write_launch_record(&attempt)?;
    }
    Ok(attempt)
}

/// The compile command choices that decide whether and how a compile is reused.
fn reuse_request<'py>(request: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let flags: Bound<'py, PyAny> = request.getattr("profile_flags")?;
    let mut profiling: bool = false;
    for name in [
        "skip_discovery_sql_analysis",
        "skip_column_inference",
        "skip_contracts",
        "skip_write",
    ] {
        profiling = profiling || flags.getattr(name)?.is_truthy()?;
    }
    let mut fields: Vec<(&str, Bound<'py, PyAny>)> = Vec::new();
    for name in [
        "project_dir",
        "selected_target",
        "json_output",
        "no_color",
        "manifest",
        "dag_path",
        "defer_to",
        "no_cache",
        "no_sql_validation",
    ] {
        fields.push((name, request.getattr(name)?));
    }
    fields.push((
        "lineage_mode",
        request
            .getattr("lineage_mode")?
            .getattr("value")?
            .str()?
            .into_any(),
    ));
    for name in ["select", "exclude", "cli_vars", "debug"] {
        fields.push((name, request.getattr(name)?));
    }
    fields.push(("profiling", profiling.into_bound_py_any(py)?));
    call_with(&imported(py, REUSE_REQUEST.0, REUSE_REQUEST.1)?, &fields)
}

/// Run one compile command request, replaying the previous compile when nothing changed.
#[pyfunction]
fn run_compile<'py>(request: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let attempt: Bound<'py, PyAny> = attempt_compile_reuse(&reuse_request(request)?)?;
    let exit_code: Bound<'py, PyAny> = attempt.getattr("exit_code")?;
    if attempt.getattr("outcome")?.eq(outcome(py, HIT)?)? && !exit_code.is_none() {
        return Ok(exit_code);
    }
    imported(py, NATIVE_MODULE, "run_compile_command")?.call1((request, attempt))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py: Python<'_> = module.py();
    module.add(RACY_WINDOW_ATTRIBUTE, RACY_WINDOW_NS)?;
    module.add(
        EXCLUDED_ROOT_ATTRIBUTE,
        PyFrozenSet::new(py, EXCLUDED_ROOT_DIRECTORIES)?,
    )?;
    module.add_function(wrap_pyfunction!(attempt_compile_reuse, module)?)?;
    module.add_function(wrap_pyfunction!(run_compile, module)?)
}
