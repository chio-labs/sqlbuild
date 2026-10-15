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
use crate::bindings::_helpers::presentation_text::terminal::stdout_supports_color;

const NATIVE_MODULE: &str = "sqlbuild._native";
const EXTERNAL_REFS_MODULE: &str = "sqlbuild._native";
const PIPELINE_MODELS: &str = "sqlbuild.compiler.pipeline.models";
const CONTRACT_MODELS: &str = "sqlbuild.runtime.contracts.models";
const PRESENTATION_MODELS: &str = "sqlbuild._native";
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
    let requested_dir: Bound<'py, PyAny> = request.getattr("project_dir")?;
    let project_dir: Bound<'py, PyAny> = if requested_dir.is_none() {
        imported(py, "pathlib", "Path")?.call_method0("cwd")?
    } else {
        requested_dir
    };
    let discovered: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "discover_project_inputs")?,
        &[
            ("project_dir", project_dir.clone()),
            ("extract_output_column_locations", flag(py, false)),
        ],
    )?;
    let preview: Bound<'py, PyDict> = PyDict::new(py);
    preview.set_item("discovered_inputs", &discovered)?;
    preview.set_item("as_target", request.getattr("as_target")?)?;
    preview.set_item("command_name", COMMAND_NAME)?;
    imported(py, NATIVE_MODULE, "validate_preview_target")?.call((), Some(&preview))?;
    let context: Bound<'py, PyAny> = resolve_adapter_connection_context(
        &discovered,
        &project_dir,
        (
            request.getattr("selected_target")?,
            request.getattr("cli_vars")?,
        ),
        true,
    )?;
    let json_output: bool = request.getattr("json_output")?.is_truthy()?;
    let use_color: bool =
        !request.getattr("no_color")?.is_truthy()? && !json_output && stdout_supports_color(py)?;
    let stream: Bound<'py, PyAny> =
        py.import("sys")?
            .getattr(if json_output { "stderr" } else { "stdout" })?;
    let connection_progress: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "ConnectionProgressReporter")?,
        &[
            ("adapter_name", context.getattr("adapter_name")?),
            ("stream", stream.clone()),
            ("use_color", flag(py, use_color)),
        ],
    )?;
    let planning_progress: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "PlanningProgressReporter")?,
        &[
            ("stream", stream.clone()),
            ("use_color", flag(py, use_color)),
        ],
    )?;
    let requested_load: Bound<'py, PyAny> = request.getattr("load_sources")?;
    let load_sources: Bound<'py, PyAny> = if requested_load.is_none() {
        call_with(
            &imported(py, NATIVE_MODULE, "build_effective_settings_config")?,
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
        &imported(py, CONTRACT_MODELS, "ConnectionHooks")?,
        &[
            (
                "on_progress",
                invocation.planning_progress.getattr("on_progress")?,
            ),
            (
                "on_connection_start",
                connection.getattr("on_connection_start")?,
            ),
            (
                "on_connection_complete",
                keyword_relay(
                    connection.getattr("on_connection_complete")?,
                    &CONNECTION_TIMING,
                )?,
            ),
            (
                "on_connection_error",
                keyword_relay(
                    connection.getattr("on_connection_error")?,
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
    let as_target: Bound<'py, PyAny> = request.getattr("as_target")?;
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
            request.getattr("selected_target")?
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
        invocation.context.getattr("connection_config")?,
    )?;
    options.set_item("external_sql_reference_resolver", resolver)?;
    options.set_item(
        "resolve_python_run_selectors",
        request.getattr("include_python")?,
    )?;
    options.set_item("record_migration_fingerprints", false)?;
    let pipeline_options: Bound<'py, PyAny> =
        imported(py, PIPELINE_MODELS, "CompilePipelineOptions")?.call((), Some(&options))?;
    call_with(
        &imported(py, NATIVE_MODULE, "run_compile_pipeline")?,
        &[
            ("discovered_inputs", invocation.discovered.clone()),
            ("adapter", invocation.context.getattr("adapter")?),
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
    let plan: Bound<'_, PyAny> = pipeline.getattr("plan_output")?;
    let python_entries: Bound<'_, PyAny> = pipeline.getattr("python_plan_entries")?;
    if request.getattr("json_output")?.is_truthy()? {
        let text: Bound<'_, PyAny> = call_with(
            &imported(py, NATIVE_MODULE, "format_plan_json")?,
            &[("plan", plan), ("python_plan_entries", python_entries)],
        )?;
        imported(py, "builtins", "print")?.call1((text,))?;
        return Ok(());
    }
    let display: Bound<'_, PyDict> = PyDict::new(py);
    display.set_item(
        "max_entries_per_section",
        if request.getattr("verbose")?.is_truthy()? {
            None
        } else {
            Some(DEFAULT_SECTION_ENTRIES)
        },
    )?;
    let text: String = call_with(
        &imported(py, NATIVE_MODULE, "format_plan")?,
        &[
            ("plan", plan),
            ("full_refresh", request.getattr("full_refresh")?),
            ("use_color", flag(py, invocation.use_color)),
            (
                "display_options",
                imported(py, PRESENTATION_MODELS, "DisplayOptions")?.call((), Some(&display))?,
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
    if !request.getattr("json_output")?.is_truthy()? {
        invocation.stream.call_method1("write", ("\n",))?;
        invocation.stream.call_method0("flush")?;
    }
    let verbose: bool = request.getattr("verbose")?.is_truthy()?;
    let pipeline: Bound<'_, PyAny> =
        with_verbose_inspection(py, verbose, || compile_pipeline(request, &invocation))?;
    write_output(request, &invocation, &pipeline)?;
    Ok(0)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_plan_command, module)?)
}
