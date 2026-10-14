//! `sqb clone`: copy or clone selected relations from an origin target into a destination target.

use std::collections::BTreeSet;
use std::time::Instant;

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyString};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::cli_text::main::format_phase_line::format_phase_line;
use sqlbuild_core::cli_text::models::CliStyle;
use sqlbuild_core::clone_text::errors::CloneTargetError;
use sqlbuild_core::clone_text::main::clone_exit_code::clone_exit_code;
use sqlbuild_core::clone_text::main::render_clone_completion::render_clone_completion;
use sqlbuild_core::clone_text::main::render_clone_header::render_clone_header;
use sqlbuild_core::clone_text::main::validate_clone_policy::validate_clone_policy;
use sqlbuild_core::clone_text::main::validate_clone_target_names::validate_clone_target_names;
use sqlbuild_core::clone_text::models::CloneItemText;

use crate::bindings::_helpers::clone::clone_execution::{
    destination_entry_count, execute_clone_plan, resource_types_by_name,
};
use crate::bindings::_helpers::clone::clone_pipeline::{ClonePipeline, prepared_clone_pipeline};
use crate::bindings::_helpers::clone::clone_progress::{clone_item_text, write_line};
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, within};

const NATIVE_MODULE: &str = "sqlbuild._native";
const ERRORS_MODULE: &str = "sqlbuild.cli.commands.exceptions";
const COLOR_MODULE: &str = "sqlbuild.presentation.main.supports_color";
const REJECT_UNIT_TESTS_MODULE: &str = "sqlbuild.compiler.pipeline.main.reject_unit_test_selectors";
const TARGET_NAME_MODULE: &str = "sqlbuild._native";
const TARGET_CONFIG_MODULE: &str = "sqlbuild._native";
const ADAPTER_NAME_MODULE: &str = "sqlbuild._native";
const ADAPTERS_MODULE: &str = "sqlbuild.cli.commands._helpers.runtime.adapters";
const EXTERNAL_REFS_MODULE: &str = "sqlbuild.cli.commands._helpers.planning.external_refs";
const PIPELINE_MODELS: &str = "sqlbuild.compiler.pipeline.models";
const LIFECYCLE_MODULE: &str = "sqlbuild.runtime.observability.classes.operation_lifecycle";
const NO_DESTINATION: (&str, &str) = (
    "C406",
    "clone requires --to when the project has no active target",
);
const NOTHING_TO_CLONE: (&str, &str) =
    ("C407", "no cloneable resources found in the selected scope");

/// The discovered project, adapter and output context of one clone.
pub(crate) struct Invocation<'py> {
    pub(crate) project_dir: Bound<'py, PyAny>,
    pub(crate) discovered: Bound<'py, PyAny>,
    pub(crate) adapter_name: String,
    pub(crate) adapter: Bound<'py, PyAny>,
    pub(crate) destination: String,
    pub(crate) style: CliStyle,
    /// The stdout of the invocation, which progress keeps writing to while output is captured.
    pub(crate) stream: Bound<'py, PyAny>,
}

fn user_error(py: Python<'_>, (code, message): (&str, &str)) -> PyErr {
    let raised = (|| {
        let options: Bound<'_, PyDict> = PyDict::new(py);
        options.set_item("code", code)?;
        imported(py, ERRORS_MODULE, "CliUserError")?.call((message,), Some(&options))
    })();
    match raised {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}

fn target_error(py: Python<'_>, error: CloneTargetError) -> PyErr {
    user_error(py, (error.code, &error.message))
}

fn text<'py>(py: Python<'py>, value: &str) -> Bound<'py, PyAny> {
    PyString::new(py, value).into_any()
}

fn progress_reporter<'py>(
    stream: &Bound<'py, PyAny>,
    style: CliStyle,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = stream.py();
    let options: Bound<'py, PyDict> = PyDict::new(py);
    options.set_item("stream", stream)?;
    options.set_item("use_color", style.use_color)?;
    imported(py, NATIVE_MODULE, "PlanningProgressReporter")?.call((), Some(&options))
}

fn lifecycle<'py>(py: Python<'py>, (kind, name): (&str, &str)) -> PyResult<Bound<'py, PyAny>> {
    call_with(
        &imported(py, LIFECYCLE_MODULE, "OperationLifecycle")?,
        &[
            ("operation_kind", text(py, kind)),
            ("operation_name", text(py, name)),
        ],
    )
}

fn target_names(discovered: &Bound<'_, PyAny>) -> PyResult<BTreeSet<String>> {
    let mut names: BTreeSet<String> = BTreeSet::new();
    for config in ["project_config", "local_config"] {
        for name in discovered.getattr(config)?.getattr("targets")?.try_iter()? {
            names.insert(name?.extract()?);
        }
    }
    Ok(names)
}

fn clone_policy(discovered: &Bound<'_, PyAny>, (target, flag): (&str, &str)) -> PyResult<bool> {
    let py: Python<'_> = discovered.py();
    call_with(
        &imported(py, TARGET_CONFIG_MODULE, "resolve_target_config")?,
        &[
            ("project_config", discovered.getattr("project_config")?),
            ("local_config", discovered.getattr("local_config")?),
            ("target_name", text(py, target)),
        ],
    )?
    .getattr("clone")?
    .getattr(flag)?
    .is_truthy()
}

/// Discover the project, resolve and validate the targets, and resolve the adapter.
fn invocation<'py>(py: Python<'py>, request: &Bound<'py, PyAny>) -> PyResult<Invocation<'py>> {
    let project_dir: Bound<'py, PyAny> = match request.getattr("project_dir")? {
        directory if !directory.is_none() => directory,
        _ => py.import("pathlib")?.getattr("Path")?.call_method0("cwd")?,
    };
    let use_color: bool = !request.getattr("no_color")?.extract::<bool>()?
        && imported(py, COLOR_MODULE, "supports_color")?
            .call0()?
            .extract::<bool>()?;
    let style: CliStyle = CliStyle { use_color };
    let stream: Bound<'py, PyAny> = py.import("sys")?.getattr("stdout")?;
    let progress: Bound<'py, PyAny> = progress_reporter(&stream, style)?;
    progress.call_method1("start", ("Discovering project...",))?;
    let discovered: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "discover_project_inputs")?,
        &[("project_dir", project_dir.clone())],
    )?;
    progress.call_method1("complete", ("Discovered project.",))?;
    call_with(
        &imported(py, REJECT_UNIT_TESTS_MODULE, "reject_unit_test_selectors")?,
        &[
            ("select", request.getattr("select")?),
            ("exclude", request.getattr("exclude")?),
            ("discovered_inputs", discovered.clone()),
        ],
    )?;
    let mut destination: Bound<'py, PyAny> = request.getattr("destination_target_name")?;
    if destination.is_none() {
        destination = call_with(
            &imported(py, TARGET_NAME_MODULE, "resolve_target_name")?,
            &[
                ("project_config", discovered.getattr("project_config")?),
                ("local_config", discovered.getattr("local_config")?),
                ("selected_target", py.None().into_bound(py)),
            ],
        )?;
    }
    if destination.is_none() {
        return Err(user_error(py, NO_DESTINATION));
    }
    let destination: String = destination.extract()?;
    let origin: String = request.getattr("origin_target_name")?.extract()?;
    let targets: (&str, &str) = (&origin, &destination);
    validate_clone_target_names(targets, &target_names(&discovered)?)
        .map_err(|error| target_error(py, error))?;
    let policy: (bool, bool) = (
        clone_policy(&discovered, (&origin, "allow_as_clone_origin"))?,
        clone_policy(&discovered, (&destination, "allow_as_clone_destination"))?,
    );
    validate_clone_policy(targets, policy).map_err(|error| target_error(py, error))?;
    let adapter_name: Bound<'py, PyAny> = call_with(
        &imported(py, ADAPTER_NAME_MODULE, "resolve_effective_adapter_name")?,
        &[
            ("project_config", discovered.getattr("project_config")?),
            ("local_config", discovered.getattr("local_config")?),
        ],
    )?;
    let adapter: Bound<'py, PyAny> = call_with(
        &imported(py, ADAPTERS_MODULE, "resolve_adapter")?,
        &[
            ("adapter_name", adapter_name.clone()),
            ("project_dir", project_dir.clone()),
        ],
    )?;
    Ok(Invocation {
        project_dir,
        discovered,
        adapter_name: adapter_name.extract()?,
        adapter,
        destination,
        style,
        stream,
    })
}

/// Resolve the destination connection config and connect, returning both.
fn connect<'py>(
    request: &Bound<'py, PyAny>,
    invocation: &Invocation<'py>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let py: Python<'py> = request.py();
    let config: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "resolve_target_connection_config")?,
        &[
            ("discovered_inputs", invocation.discovered.clone()),
            ("project_dir", invocation.project_dir.clone()),
            ("target_name", text(py, &invocation.destination)),
            ("cli_vars", request.getattr("cli_vars")?),
        ],
    )?;
    let progress: Bound<'py, PyAny> = progress_reporter(&invocation.stream, invocation.style)?;
    progress.call_method1(
        "start",
        (format!("Connecting to {}...", invocation.adapter_name),),
    )?;
    let started: Instant = Instant::now();
    let connection: Bound<'py, PyAny> = within(
        &lifecycle(py, ("clone", "clone_target_connection"))?,
        |_| invocation.adapter.call_method1("connect", (&config,)),
    )?;
    let summary: String = format!(
        "{}  ({:.2}s)",
        invocation.adapter_name,
        started.elapsed().as_secs_f64()
    );
    progress.call_method1(
        "complete_styled",
        (format_phase_line(
            invocation.style,
            true,
            ("Warehouse connected", &summary),
        ),),
    )?;
    Ok((config, connection))
}

/// Run the clone pipeline and refuse an empty selection.
fn prepare<'py>(
    request: &Bound<'py, PyAny>,
    invocation: &Invocation<'py>,
    (config, connection): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let progress: Bound<'py, PyAny> = progress_reporter(&invocation.stream, invocation.style)?;
    let started: Instant = Instant::now();
    let pipeline: Bound<'py, PyAny> =
        within(&lifecycle(py, ("project", "project_compile"))?, |_| {
            progress.call_method1("on_progress", ("Preparing clone plan...",))?;
            let resolver: Bound<'py, PyAny> = call_with(
                &imported(
                    py,
                    EXTERNAL_REFS_MODULE,
                    "resolve_external_sql_reference_resolver",
                )?,
                &[
                    ("project_dir", invocation.project_dir.clone()),
                    ("discovered_inputs", invocation.discovered.clone()),
                ],
            )?;
            let destination_connection: Bound<'py, PyAny> = call_with(
                &imported(py, PIPELINE_MODELS, "ClonePipelineConnection")?,
                &[("config", config.clone()), ("handle", connection.clone())],
            )?;
            let options: Bound<'py, PyAny> = call_with(
                &imported(py, PIPELINE_MODELS, "ClonePipelineOptions")?,
                &[
                    ("no_sql_validation", request.getattr("no_sql_validation")?),
                    ("select", request.getattr("select")?),
                    ("exclude", request.getattr("exclude")?),
                    ("cli_vars", request.getattr("cli_vars")?),
                ],
            )?;
            let pipeline: Bound<'py, PyAny> = prepared_clone_pipeline(
                &ClonePipeline {
                    discovered: invocation.discovered.clone(),
                    adapter: invocation.adapter.clone(),
                    connection: destination_connection,
                    options,
                    resolver,
                },
                (
                    &request.getattr("origin_target_name")?,
                    &text(py, &invocation.destination),
                ),
            )?;
            progress.call_method1(
                "on_progress",
                (format!(
                    "Prepared clone plan. ({:.2}s)",
                    started.elapsed().as_secs_f64()
                ),),
            )?;
            Ok(pipeline)
        })?;
    if destination_entry_count(&pipeline)? == 0 {
        return Err(user_error(py, NOTHING_TO_CLONE));
    }
    Ok(pipeline)
}

/// Prepare, announce and execute the clone with an open destination connection.
fn clone<'py>(
    request: &Bound<'py, PyAny>,
    invocation: &Invocation<'py>,
    (config, connection): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>, f64)> {
    let pipeline: Bound<'py, PyAny> = prepare(request, invocation, (config, connection))?;
    let origin: String = request.getattr("origin_target_name")?.extract()?;
    write_line(
        &invocation.stream,
        &render_clone_header(
            (&origin, &invocation.destination),
            destination_entry_count(&pipeline)?,
            invocation.style,
        ),
    )?;
    let (result, elapsed) = execute_clone_plan(request, invocation, (&pipeline, connection))?;
    Ok((pipeline, result, elapsed))
}

/// Run one `sqb clone` request.
#[pyfunction]
#[pyo3(signature = (*, request))]
fn run_clone_command(py: Python<'_>, request: &Bound<'_, PyAny>) -> PyResult<i32> {
    let invocation: Invocation<'_> = invocation(py, request)?;
    let (config, connection) = connect(request, &invocation)?;
    let outcome = clone(request, &invocation, (&config, &connection));
    let closed: PyResult<Bound<'_, PyAny>> =
        invocation.adapter.call_method1("close", (&connection,));
    let (pipeline, result, elapsed) = outcome?;
    closed?;
    let items: Vec<CloneItemText> = result
        .getattr("item_results")?
        .try_iter()?
        .map(|item| clone_item_text(&item?))
        .collect::<PyResult<_>>()?;
    let stdout: Bound<'_, PyAny> = py.import("sys")?.getattr("stdout")?;
    for line in render_clone_completion(&items, Some(elapsed), invocation.style).lines() {
        if !line.is_empty() {
            stdout.call_method1("write", (line,))?;
        }
        stdout.call_method1("write", ("\n",))?;
    }
    let resource_types: Bound<'_, PyDict> = PyDict::new(py);
    for (name, resource_type) in resource_types_by_name(&pipeline)? {
        resource_types.set_item(name, resource_type)?;
    }
    let payload: Bound<'_, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "format_clone_execution_json")?,
        &[
            ("result", result.clone()),
            ("resource_types_by_name", resource_types.into_any()),
        ],
    )?;
    call_with(
        &imported(py, NATIVE_MODULE, "write_execution_json_output")?,
        &[
            ("payload", payload),
            ("json_output", PyBool::new(py, false).to_owned().into_any()),
            ("json_output_path", request.getattr("json_output_path")?),
        ],
    )?;
    Ok(clone_exit_code(&items))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_clone_command, module)?)?;
    Ok(())
}
