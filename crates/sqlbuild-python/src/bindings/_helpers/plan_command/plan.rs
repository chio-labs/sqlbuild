//! `sqb plan`: compile the plan pipeline and print the plan as text or JSON.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python, pyfunction,
};
use pyo3::types::{PyBool, PyDict, PyDictMethods};
use pyo3::wrap_pyfunction;

use crate::bindings::_helpers::build_command::support::keyword_relay;
use crate::bindings::_helpers::cli::progress_text::with_verbose_inspection;
use crate::bindings::_helpers::command_runtime::invocation::resolve_adapter_connection_context;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::native_host::executor::ExecutorHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::presentation_text::terminal::stdout_supports_color;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;

const COMMAND_NAME: &str = "plan";
const DEFAULT_SECTION_ENTRIES: i64 = 50;
const CONNECTION_TIMING: [&str; 2] = ["connection_count", "elapsed_seconds"];
/// Request fields passed to the compile pipeline under the same name.
const PIPELINE_FIELDS: [&str; 11] = [
    "no_sql_validation",
    "no_cache",
    "defer_to",
    "defer_sources_to",
    "cursor_overrides",
    "full_refresh",
    "select",
    "exclude",
    "cli_vars",
    "max_microbatches",
    "selection_diagnostics",
];

fn flag(py: Python<'_>, value: bool) -> Bound<'_, PyAny> {
    PyBool::new(py, value).to_owned().into_any()
}

fn print_line(py: Python<'_>, text: &str) -> PyResult<()> {
    imported(py, "builtins", "print")?.call1((text,))?;
    Ok(())
}

/// The discovered project, adapter context, output stream and progress reporters of one plan.
struct PlanInvocation<'py> {
    project_dir: Bound<'py, PyAny>,
    discovered: Bound<'py, PyAny>,
    context: Bound<'py, PyAny>,
    stream: Bound<'py, PyAny>,
    use_color: bool,
    connection_progress: Bound<'py, PyAny>,
    planning_progress: Bound<'py, PyAny>,
    load_sources: Bound<'py, PyAny>,
}

fn resolve_invocation<'py>(request: &Bound<'py, PyAny>) -> PyResult<PlanInvocation<'py>> {
    let py: Python<'py> = request.py();
    let requested_dir: Bound<'py, PyAny> = native_field(request, "project_dir")?;
    let project_dir: Bound<'py, PyAny> = if requested_dir.is_none() {
        imported(py, "pathlib", "Path")?.call_method0("cwd")?
    } else {
        requested_dir
    };
    let discovered: Bound<'py, PyAny> = call_with(
        &registry::native(py, NativeAttr::DiscoverProjectInputs)?,
        &[
            ("project_dir", project_dir.clone()),
            ("extract_output_column_locations", flag(py, false)),
        ],
    )?;
    let preview: Bound<'py, PyDict> = PyDict::new(py);
    preview.set_item("discovered_inputs", &discovered)?;
    preview.set_item("as_target", native_field(request, "as_target")?)?;
    preview.set_item("command_name", COMMAND_NAME)?;
    registry::native(py, NativeAttr::ValidatePreviewTarget)?.call((), Some(&preview))?;
    let context: Bound<'py, PyAny> = resolve_adapter_connection_context(
        &discovered,
        &project_dir,
        (
            native_field(request, "selected_target")?,
            native_field(request, "cli_vars")?,
        ),
        true,
    )?;
    let json_output: bool = native_field(request, "json_output")?.is_truthy()?;
    let use_color: bool = !native_field(request, "no_color")?.is_truthy()?
        && !json_output
        && stdout_supports_color(py)?;
    let stream: Bound<'py, PyAny> =
        py.import("sys")?
            .getattr(if json_output { "stderr" } else { "stdout" })?;
    let connection_progress: Bound<'py, PyAny> = call_with(
        &registry::native(py, NativeAttr::ConnectionProgressReporter)?,
        &[
            ("adapter_name", native_field(&context, "adapter_name")?),
            ("stream", stream.clone()),
            ("use_color", flag(py, use_color)),
        ],
    )?;
    let planning_progress: Bound<'py, PyAny> = call_with(
        &registry::native(py, NativeAttr::PlanningProgressReporter)?,
        &[
            ("stream", stream.clone()),
            ("use_color", flag(py, use_color)),
        ],
    )?;
    let requested_load: Bound<'py, PyAny> = native_field(request, "load_sources")?;
    let load_sources: Bound<'py, PyAny> = if requested_load.is_none() {
        call_with(
            &registry::native(py, NativeAttr::BuildEffectiveSettingsConfig)?,
            &[("discovered_inputs", discovered.clone())],
        )?
        .getattr("auto_load_sources")?
    } else {
        requested_load
    };
    Ok(PlanInvocation {
        project_dir,
        discovered,
        context,
        stream,
        use_color,
        connection_progress,
        planning_progress,
        load_sources,
    })
}

/// A `ConnectionHooks` forwarding to the plan's progress reporters.
fn connection_hooks<'py>(invocation: &PlanInvocation<'py>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = invocation.stream.py();
    let connection: &Bound<'py, PyAny> = &invocation.connection_progress;
    call_with(
        &host::entry(py, ExecutorHost::ConnectionHooks)?,
        &[
            (
                "on_progress",
                native_field(&invocation.planning_progress, "on_progress")?,
            ),
            (
                "on_connection_start",
                native_field(connection, "on_connection_start")?,
            ),
            (
                "on_connection_complete",
                keyword_relay(
                    native_field(connection, "on_connection_complete")?,
                    &CONNECTION_TIMING,
                )?,
            ),
            (
                "on_connection_error",
                keyword_relay(
                    native_field(connection, "on_connection_error")?,
                    &CONNECTION_TIMING,
                )?,
            ),
        ],
    )
}

fn compile_pipeline<'py>(
    request: &Bound<'py, PyAny>,
    invocation: &PlanInvocation<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let resolver: Bound<'py, PyAny> = call_with(
        &registry::native(py, NativeAttr::ResolveExternalSqlReferenceResolver)?,
        &[
            ("project_dir", invocation.project_dir.clone()),
            ("discovered_inputs", invocation.discovered.clone()),
        ],
    )?;
    let as_target: Bound<'py, PyAny> = native_field(request, "as_target")?;
    if !as_target.is_none() {
        invocation.stream.call_method1(
            "write",
            (format!(
                "Previewing plan as target '{}' through the active target's connection (inspection only).\n",
                as_target.str()?
            ),),
        )?;
        invocation.stream.call_method0("flush")?;
    }
    let options: Bound<'py, PyDict> = PyDict::new(py);
    options.set_item(
        "selected_target",
        if as_target.is_none() {
            native_field(request, "selected_target")?
        } else {
            as_target
        },
    )?;
    for field in PIPELINE_FIELDS {
        options.set_item(field, request.getattr(field)?)?;
    }
    options.set_item("auto_load_sources", &invocation.load_sources)?;
    options.set_item(
        "connection_config",
        native_field(&invocation.context, "connection_config")?,
    )?;
    options.set_item("external_sql_reference_resolver", resolver)?;
    options.set_item(
        "resolve_python_run_selectors",
        native_field(request, "include_python")?,
    )?;
    options.set_item("record_migration_fingerprints", false)?;
    let pipeline_options: Bound<'py, PyAny> =
        registry::class(py, RecordId::CompilePipelineOptions)?.call((), Some(&options))?;
    call_with(
        &registry::native(py, NativeAttr::RunCompilePipeline)?,
        &[
            ("discovered_inputs", invocation.discovered.clone()),
            ("adapter", native_field(&invocation.context, "adapter")?),
            ("options", pipeline_options),
            ("hooks", connection_hooks(invocation)?),
        ],
    )
}

fn write_output(
    request: &Bound<'_, PyAny>,
    invocation: &PlanInvocation<'_>,
    pipeline: &Bound<'_, PyAny>,
) -> PyResult<()> {
    let py: Python<'_> = request.py();
    let plan: Bound<'_, PyAny> = native_field(pipeline, "plan_output")?;
    let python_entries: Bound<'_, PyAny> = native_field(pipeline, "python_plan_entries")?;
    if native_field(request, "json_output")?.is_truthy()? {
        let text: Bound<'_, PyAny> = call_with(
            &registry::native(py, NativeAttr::FormatPlanJson)?,
            &[("plan", plan), ("python_plan_entries", python_entries)],
        )?;
        imported(py, "builtins", "print")?.call1((text,))?;
        return Ok(());
    }
    let display: Bound<'_, PyDict> = PyDict::new(py);
    display.set_item(
        "max_entries_per_section",
        if native_field(request, "verbose")?.is_truthy()? {
            None
        } else {
            Some(DEFAULT_SECTION_ENTRIES)
        },
    )?;
    let text: String = call_with(
        &registry::native(py, NativeAttr::FormatPlan)?,
        &[
            ("plan", plan),
            ("full_refresh", native_field(request, "full_refresh")?),
            ("use_color", flag(py, invocation.use_color)),
            (
                "display_options",
                registry::class(py, RecordId::DisplayOptions)?.call((), Some(&display))?,
            ),
            ("python_plan_entries", python_entries),
            ("include_direct_freshness_diagnostics", flag(py, false)),
            ("include_completion", flag(py, true)),
        ],
    )?
    .extract()?;
    print_line(py, &format!("\n{text}"))
}

/// Run one `sqb plan` request.
#[pyfunction]
#[pyo3(signature = (*, request))]
fn run_plan_command(request: &Bound<'_, PyAny>) -> PyResult<i32> {
    let py: Python<'_> = request.py();
    let invocation: PlanInvocation<'_> = resolve_invocation(request)?;
    if !native_field(request, "json_output")?.is_truthy()? {
        invocation.stream.call_method1("write", ("\n",))?;
        invocation.stream.call_method0("flush")?;
    }
    let verbose: bool = native_field(request, "verbose")?.is_truthy()?;
    let pipeline: Bound<'_, PyAny> =
        with_verbose_inspection(py, verbose, || compile_pipeline(request, &invocation))?;
    write_output(request, &invocation, &pipeline)?;
    Ok(0)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_plan_command, module)?)
}
