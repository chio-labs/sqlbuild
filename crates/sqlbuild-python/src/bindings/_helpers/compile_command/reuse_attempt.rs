//! Check whether a compile can replay the stored result, replay it on a hit and leave a launch record.

use std::path::PathBuf;

use pyo3::exceptions::PyOSError;
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyList, PyString};
use pyo3::{IntoPyObjectExt, pyfunction, wrap_pyfunction};
use sqlbuild_cli::replay::main::write_launch_record::write_launch_record as write_record_file;

use crate::bindings::_helpers::compile_driver::phases::{elapsed_ms, monotonic};
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, keywords};
use crate::bindings::_helpers::compile_outputs::json_report::plain_json;
use crate::bindings::_helpers::presentation_text::terminal::stdout_supports_color;

const NATIVE_MODULE: &str = "sqlbuild._native";
const REUSE_CONSTANTS: &str = "sqlbuild.cli.compile_reuse.constants";
const REUSE_MODELS: &str = "sqlbuild.cli.compile_reuse.models";
const REUSE_TYPES: &str = "sqlbuild.cli.compile_reuse.types";
const COMPILE_CONSTANTS: &str = "sqlbuild.compiler.compile.constants";
const RUNTIME_IDENTITY_MODULE: &str = "sqlbuild.cli.compile_reuse._helpers.runtime_identity";
const STARTUP_INPUTS_MODULE: &str = "sqlbuild.cli.compile_reuse._helpers.startup_inputs";
const CACHE_DIRECTORY_MODULE: &str = "sqlbuild.compiler.frontier.main.compiler_cache_directory";
const LAUNCH_RECORD_PATH_MODULE: &str = "sqlbuild.cli.entry.main._launch_record_path";
const COMPUTE_LOG_TEE_MODULE: &str = "sqlbuild.runtime.compute_logs.classes.text_tee";
const OUTPUT_CAPTURE_CONSTANTS: &str = "sqlbuild.runtime.output_capture.constants";
const SECONDS_FIELD: &str = "{seconds:.1f}";
const HIT: &str = "HIT";
const CHECKED_HIT: &str = "hit";
const CHECKED_BYPASS: &str = "bypass";
const MISS: &str = "MISS";
const BYPASS: &str = "BYPASS";

fn constant<'py>(py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyAny>> {
    imported(py, REUSE_CONSTANTS, name)
}

fn sorted<'py>(value: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    imported(value.py(), "builtins", "sorted")?.call1((value,))
}

fn listed<'py>(value: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    Ok(PyList::new(value.py(), value.try_iter()?.collect::<PyResult<Vec<_>>>()?)?.into_any())
}

fn reuse_logger(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    imported(py, "logging", "getLogger")?.call1((constant(py, "REUSE_LOGGER_NAME")?,))
}

/// The reuse constants the native check, the stored compile and the launch record share.
pub(crate) fn reuse_rules(py: Python<'_>, with_output_files: bool) -> PyResult<Bound<'_, PyDict>> {
    let rules: Bound<'_, PyDict> = PyDict::new(py);
    rules.set_item("excluded", sorted(constant(py, "EXCLUDED_DIRECTORIES")?)?)?;
    rules.set_item(
        "excluded_root",
        sorted(constant(py, "EXCLUDED_ROOT_DIRECTORIES")?)?,
    )?;
    rules.set_item(
        "presence_suffixes",
        listed(constant(py, "PRESENCE_ONLY_FILE_SUFFIXES")?)?,
    )?;
    let output_files: Bound<'_, PyAny> =
        imported(py, RUNTIME_IDENTITY_MODULE, "redirected_output_files")?.call0()?;
    if with_output_files {
        rules.set_item("output_files", output_files)?;
    }
    rules.set_item(
        "tracked_prefixes",
        listed(constant(py, "TRACKED_ENVIRONMENT_PREFIXES")?)?,
    )?;
    rules.set_item(
        "untracked_names",
        sorted(constant(py, "UNTRACKED_ENVIRONMENT_NAMES")?)?,
    )?;
    rules.set_item(
        "disabling_variables",
        PyList::new(
            py,
            [
                (
                    imported(py, COMPILE_CONSTANTS, "COMPILE_CACHE_DISABLE_ENV_VAR")?,
                    imported(py, COMPILE_CONSTANTS, "COMPILE_CACHE_DISABLE_VALUE")?,
                ),
                (
                    constant(py, "REUSE_DISABLE_ENV_VAR")?,
                    constant(py, "REUSE_DISABLE_VALUE")?,
                ),
            ],
        )?,
    )?;
    rules.set_item(
        "config_filenames",
        listed(constant(py, "PROJECT_CONFIG_FILENAMES")?)?,
    )?;
    for (key, name) in [
        ("racy_window_ns", "RACY_WINDOW_NS"),
        ("max_stored_entries", "REUSE_MAX_STORED_ENTRIES"),
        ("max_entry_bytes", "REUSE_MAX_ENTRY_BYTES"),
        ("missing_environment_value", "MISSING_ENVIRONMENT_VALUE"),
        ("missing_file_digest", "MISSING_FILE_DIGEST"),
        ("missing_path_mtime_ns", "MISSING_PATH_MTIME_NS"),
        ("project_root_path_mtime_ns", "PROJECT_ROOT_PATH_MTIME_NS"),
    ] {
        rules.set_item(key, constant(py, name)?)?;
    }
    rules.set_item(
        "compiled_root",
        imported(py, "os.path", "join")?.call1((
            constant(py, "TARGET_DIRECTORY_NAME")?,
            constant(py, "COMPILED_DIRECTORY_NAME")?,
        ))?,
    )?;
    rules.set_item(
        "retired_directories",
        PyList::new(py, [constant(py, "RETIRED_REUSE_DIRECTORY_NAME")?])?,
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
            .call_method1(
                "__truediv__",
                (constant(py, "COMPUTE_LOG_DIRECTORY_NAME")?,),
            )?
            .call_method0("resolve")?;
        let capture: Bound<'py, PyDict> = PyDict::new(py);
        capture.set_item("root", logs.str()?)?;
        capture.set_item("command", constant(py, "COMPILE_COMMAND_NAME")?)?;
        capture.set_item("project_dir", resolved.str()?)?;
        capture.set_item("target", attempt.getattr("selected_target")?)?;
        capture.into_any()
    } else {
        py.None().into_bound(py)
    };
    let hit_message: Bound<'py, PyAny> =
        constant(py, "REUSE_HIT_MESSAGE")?.call_method1("split", (SECONDS_FIELD,))?;
    let timings: Bound<'py, PyDict> = PyDict::new(py);
    for (key, name) in [
        ("hit", "REUSE_HIT_TIMING"),
        ("miss", "REUSE_MISS_TIMING"),
        ("bypass", "REUSE_BYPASS_TIMING"),
        ("check", "REUSE_CHECK_TIMING"),
        ("total", "TOTAL_TIMING"),
    ] {
        timings.set_item(key, constant(py, name)?)?;
    }
    let payload: Bound<'py, PyDict> = PyDict::new(py);
    payload.set_item("format", constant(py, "LAUNCH_RECORD_FORMAT")?)?;
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
    payload.set_item("hit_message", listed(hit_message)?)?;
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
    let path: Bound<'_, PyAny> =
        imported(py, LAUNCH_RECORD_PATH_MODULE, "launch_record_path")?.call0()?;
    let native: Bound<'_, PyAny> = attempt.getattr("native")?;
    if path.is_none() || native.is_none() {
        return Ok(());
    }
    let environment: Bound<'_, PyAny> = imported(py, "os", "environ")?;
    if environment.contains(imported(
        py,
        OUTPUT_CAPTURE_CONSTANTS,
        "INVOCATION_CONTEXT_ENV",
    )?)? {
        return Ok(());
    }
    let mut directory: Bound<'_, PyAny> = attempt.getattr("project_dir")?;
    for part in constant(py, "LAUNCH_RECORD_DIRECTORY")?.try_iter()? {
        directory = directory.call_method1("__truediv__", (part?,))?;
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
    imported(py, REUSE_TYPES, "CompileReuseOutcome")?.getattr(name)
}

/// A `CompileReuseAttempt` with `fields`.
fn reuse_attempt<'py>(
    py: Python<'py>,
    fields: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    call_with(&imported(py, REUSE_MODELS, "CompileReuseAttempt")?, fields)
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
        imported(py, CACHE_DIRECTORY_MODULE, "compiler_cache_directory")?
            .call1((imported(py, "pathlib", "Path")?.call1((project_dir,))?,))?
            .call_method1(
                "__truediv__",
                (constant(py, "NATIVE_REUSE_DIRECTORY_NAME")?,),
            )?,
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
    let mut timings: Vec<(Bound<'py, PyAny>, i64)> = Vec::new();
    for (name, counted) in [
        ("REUSE_HIT_TIMING", 1),
        ("REUSE_MISS_TIMING", 0),
        ("REUSE_BYPASS_TIMING", 0),
        ("REUSE_CHECK_TIMING", check_ms),
    ] {
        timings.push((constant(py, name)?, counted));
    }
    timings.push((constant(py, "TOTAL_TIMING")?, elapsed_ms(py, started)?));
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
    let seconds: Bound<'py, PyAny> = check_ms
        .into_bound_py_any(py)?
        .call_method1("__truediv__", (constant(py, "MILLISECONDS_PER_SECOND")?,))?;
    print_stderr(
        py,
        &constant(py, "REUSE_HIT_MESSAGE")?.call_method(
            "format",
            (),
            Some(&keywords(py, &[("seconds", seconds)])?),
        )?,
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

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(attempt_compile_reuse, module)?)
}
