//! Discovery, adapter, connection and output context for project commands that connect.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::PyBool;

use crate::bindings::_helpers::command_runtime::adapters::resolve_cli_adapter;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::presentation_text::terminal::stdout_supports_color;

const NATIVE_MODULE: &str = "sqlbuild._native";
const NATIVE_RECORDS: &str = "sqlbuild._native";

/// The project directory, discovered inputs, adapter context, colour and progress stream.
type InvocationContext<'py> = (
    Bound<'py, PyAny>,
    Bound<'py, PyAny>,
    Bound<'py, PyAny>,
    bool,
    Bound<'py, PyAny>,
);

fn boolean(py: Python<'_>, value: bool) -> Bound<'_, PyAny> {
    PyBool::new(py, value).to_owned().into_any()
}

/// The effective adapter and project connection configuration as an `AdapterConnectionContext`.
pub(crate) fn resolve_adapter_connection_context<'py>(
    discovered: &Bound<'py, PyAny>,
    project_dir: &Bound<'py, PyAny>,
    (selected_target, cli_vars): (Bound<'py, PyAny>, Bound<'py, PyAny>),
    require_connection: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = discovered.py();
    let adapter_name: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "resolve_effective_adapter_name")?,
        &[
            ("project_config", discovered.getattr("project_config")?),
            ("local_config", discovered.getattr("local_config")?),
        ],
    )?;
    let adapter: Bound<'py, PyAny> = resolve_cli_adapter(&adapter_name, project_dir)?;
    let connection_config: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "resolve_project_connection_config")?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("project_dir", project_dir.clone()),
            ("selected_target", selected_target),
            ("cli_vars", cli_vars),
            ("require_connection", boolean(py, require_connection)),
        ],
    )?;
    call_with(
        &imported(py, NATIVE_RECORDS, "AdapterConnectionContext")?,
        &[
            ("adapter_name", adapter_name),
            ("adapter", adapter),
            ("connection_config", connection_config),
        ],
    )
}

fn invocation_context<'py>(
    request: &Bound<'py, PyAny>,
    require_connection: bool,
) -> PyResult<InvocationContext<'py>> {
    let py: Python<'py> = request.py();
    let requested: Bound<'py, PyAny> = request.getattr("project_dir")?;
    let project_dir: Bound<'py, PyAny> = if requested.is_none() {
        imported(py, "pathlib", "Path")?.call_method0("cwd")?
    } else {
        requested
    };
    let discovered: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "discover_project_inputs")?,
        &[("project_dir", project_dir.clone())],
    )?;
    let adapter_context: Bound<'py, PyAny> = resolve_adapter_connection_context(
        &discovered,
        &project_dir,
        (
            request.getattr("selected_target")?,
            request.getattr("cli_vars")?,
        ),
        require_connection,
    )?;
    let machine_output: bool = request.getattr("json_output")?.is_truthy()?;
    let use_color: bool =
        !request.getattr("no_color")?.is_truthy()? && !machine_output && stdout_supports_color(py)?;
    let stream: Bound<'py, PyAny> =
        py.import("sys")?
            .getattr(if machine_output { "stderr" } else { "stdout" })?;
    Ok((project_dir, discovered, adapter_context, use_color, stream))
}

fn context_fields<'py>(
    context: &InvocationContext<'py>,
) -> PyResult<Vec<(&'static str, Bound<'py, PyAny>)>> {
    let (project_dir, discovered, adapter_context, use_color, stream) = context;
    let py: Python<'py> = project_dir.py();
    Ok(vec![
        ("effective_project_dir", project_dir.clone()),
        ("discovered_inputs", discovered.clone()),
        ("adapter_name", adapter_context.getattr("adapter_name")?),
        ("adapter", adapter_context.getattr("adapter")?),
        (
            "connection_config",
            adapter_context.getattr("connection_config")?,
        ),
        ("use_color", boolean(py, *use_color)),
        ("progress_stream", stream.clone()),
    ])
}

/// `invocation_type(...)` with discovery, adapter, connection and output context.
pub(crate) fn resolve_command_invocation<'py>(
    request: &Bound<'py, PyAny>,
    invocation_type: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let context: InvocationContext<'py> = invocation_context(request, true)?;
    call_with(invocation_type, &context_fields(&context)?)
}

/// `invocation_type(...)` with command context plus connection and planning progress reporters.
pub(crate) fn resolve_reported_command_invocation<'py>(
    request: &Bound<'py, PyAny>,
    invocation_type: &Bound<'py, PyAny>,
    require_connection: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let context: InvocationContext<'py> = invocation_context(request, require_connection)?;
    let (_, _, adapter_context, use_color, stream) = &context;
    let mut fields: Vec<(&str, Bound<'py, PyAny>)> = context_fields(&context)?;
    fields.push((
        "connection_progress",
        call_with(
            &imported(py, NATIVE_MODULE, "ConnectionProgressReporter")?,
            &[
                ("adapter_name", adapter_context.getattr("adapter_name")?),
                ("stream", stream.clone()),
                ("use_color", boolean(py, *use_color)),
            ],
        )?,
    ));
    fields.push((
        "planning_progress",
        call_with(
            &imported(py, NATIVE_MODULE, "PlanningProgressReporter")?,
            &[
                ("stream", stream.clone()),
                ("use_color", boolean(py, *use_color)),
            ],
        )?,
    ));
    call_with(invocation_type, &fields)
}
