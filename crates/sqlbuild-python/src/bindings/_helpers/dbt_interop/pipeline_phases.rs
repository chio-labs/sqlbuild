//! dbt execution phases, live SQLBuild planning and executor handoff.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::PyDict;
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::build_command::support::{boolean, emit, none, text, tuple};
use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported, keywords,
};
use crate::bindings::_helpers::dbt_interop::pipeline_prologue::progress;
use crate::bindings::_helpers::dbt_interop::plan_output::{connection_config, connection_hooks};

const MODELS: &str = "sqlbuild.integrations.dbt.models";
const OPTIONS: (&[&str], &[&str]) = (
    &["request", "invocation"],
    &[
        "compiled",
        "plan",
        "merged_dbt_argv",
        "execution",
        "manifest",
        "failed_sqlbuild_model_names",
        "plan_output",
        "connection_config",
        "message",
    ],
);

fn environment<'py>(args: &KeywordArguments<'py>) -> PyResult<Bound<'py, PyAny>> {
    let request = args.value("request")?;
    let compiled = args.value("compiled")?;
    call_with(
        &imported(request.py(), MODELS, "DbtPlanEnvironment")?,
        &[
            ("project_dir", request.getattr("project_dir")?),
            (
                "discovered_inputs",
                args.value("invocation")?.getattr("discovered_inputs")?,
            ),
            ("project", compiled.getattr("project")?),
            ("adapter", compiled.getattr("adapter")?),
            ("adapter_name", compiled.getattr("adapter_name")?),
        ],
    )
}

/// Resolve the selected SQLBuild work's effective connection configuration.
#[pyfunction]
#[pyo3(signature = (**options))]
fn resolve_dbt_connection_config<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(py, "resolve_dbt_connection_config", options, OPTIONS)?;
    connection_config(&environment(&args)?)
}

/// Render the merged selection unless the command is producing JSON.
#[pyfunction]
#[pyo3(signature = (**options))]
fn write_dbt_execution_plan_text(
    py: Python<'_>,
    options: Option<Bound<'_, PyDict>>,
) -> PyResult<()> {
    let args = KeywordArguments::read(py, "write_dbt_execution_plan_text", options, OPTIONS)?;
    let request = args.value("request")?;
    if request.getattr("json_output")?.is_truthy()? {
        return Ok(());
    }
    let plan = args.value("plan")?;
    let merged = args.value("merged_dbt_argv")?;
    let display = if merged.is_none() {
        plan
    } else {
        imported(py, "dataclasses", "replace")?.call(
            (plan,),
            Some(&keywords(
                py,
                &[
                    ("dbt_command_argv", merged),
                    ("supplemental_dbt_command_argvs", tuple(py, &[])?),
                ],
            )?),
        )?
    };
    let limit = if request.getattr("verbose")?.is_truthy()? {
        none(py)
    } else {
        pyo3::types::PyInt::new(py, super::constants::PLAN_DISPLAY_LIMIT).into_any()
    };
    let rendered = call_with(
        &imported(py, "sqlbuild._native", "render_dbt_interop_plan")?,
        &[
            ("plan", display),
            ("json_output", boolean(py, false)),
            ("use_color", request.getattr("use_color")?),
            (
                "display_options",
                call_with(
                    &imported(py, "sqlbuild.presentation.models", "DisplayOptions")?,
                    &[("max_entries_per_section", limit)],
                )?,
            ),
        ],
    )?;
    emit(
        &args.value("invocation")?.getattr("output_stream")?,
        &format!("{}\n\n", rendered.extract::<String>()?),
    )
}

/// Execute dbt without introducing any SQLBuild state callbacks.
#[pyfunction]
#[pyo3(signature = (**options))]
fn execute_dbt_without_state_tracking<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(py, "execute_dbt_without_state_tracking", options, OPTIONS)?;
    let request = args.value("request")?;
    let invocation = args.value("invocation")?;
    call_with(
        &imported(py, "sqlbuild._native", "execute_dbt_commands")?,
        &[
            ("runner", invocation.getattr("runner")?),
            ("options", invocation.getattr("dbt_options")?),
            ("merged_argv", args.value("merged_dbt_argv")?),
            ("progress_stream", invocation.getattr("output_stream")?),
            ("stdout_stream", invocation.getattr("dbt_output_stream")?),
            ("use_color", request.getattr("use_color")?),
            (
                "skip_message",
                text(py, "Skipping dbt: no dbt work selected."),
            ),
            ("on_progress", request.getattr("on_progress")?),
        ],
    )
}

/// Write the summary of actual dbt execution events.
#[pyfunction]
#[pyo3(signature = (**options))]
fn write_dbt_execution_summary(py: Python<'_>, options: Option<Bound<'_, PyDict>>) -> PyResult<()> {
    let args = KeywordArguments::read(py, "write_dbt_execution_summary", options, OPTIONS)?;
    let footer = call_with(
        &imported(
            py,
            "sqlbuild._native",
            "render_dbt_execution_summary_footer",
        )?,
        &[
            (
                "node_results",
                args.value("execution")?.getattr("node_results")?,
            ),
            ("use_color", args.value("request")?.getattr("use_color")?),
        ],
    )?;
    if !footer.is_none() {
        emit(
            &args.value("invocation")?.getattr("output_stream")?,
            &format!("\n{}\n", footer.extract::<String>()?),
        )?;
    }
    Ok(())
}

/// Plan SQLBuild work after dbt using actual dbt failures as external blockers.
#[pyfunction]
#[pyo3(signature = (**options))]
fn resolve_sqlbuild_execution_plan_output<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "resolve_sqlbuild_execution_plan_output",
        options,
        OPTIONS,
    )?;
    let plan = args.value("plan")?;
    if !plan.getattr("sqlbuild_skip_reason")?.is_none() {
        return Ok(none(py));
    }
    let selected = plan.getattr("selection")?.getattr("sqlbuild_model_names")?;
    if !selected.is_truthy()? {
        return Ok(none(py));
    }
    let invocation = args.value("invocation")?;
    let stream = invocation.getattr("output_stream")?;
    emit(&stream, "\n")?;
    let reporter = call_with(
        &imported(py, "sqlbuild._native", "ConnectionProgressReporter")?,
        &[
            (
                "adapter_name",
                args.value("compiled")?.getattr("adapter_name")?,
            ),
            ("stream", stream),
            ("blank_line_after_complete", boolean(py, true)),
            ("use_color", args.value("request")?.getattr("use_color")?),
        ],
    )?;
    let request = call_with(
        &imported(py, MODELS, "DbtSqlbuildPlanRequest")?,
        &[
            ("selected_model_names", selected),
            (
                "sqlbuild_args",
                invocation.getattr("effective_sqlbuild_args")?,
            ),
            (
                "external_blocked_model_names",
                args.value("failed_sqlbuild_model_names")?,
            ),
        ],
    )?;
    call_with(
        &imported(py, "sqlbuild._native", "build_sqlbuild_plan_output")?,
        &[
            ("environment", environment(&args)?),
            ("request", request),
            ("hooks", connection_hooks(&reporter, none(py))?),
        ],
    )
}

fn execution_limits<'py>(
    discovered: &Bound<'py, PyAny>,
    target: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = discovered.py();
    if target.is_none() {
        return imported(
            py,
            "sqlbuild.spec.contracts.models",
            "ExecutionLimitsConfig",
        )?
        .call0();
    }
    call_with(
        &imported(py, "sqlbuild._native", "resolve_target_config")?,
        &[
            ("project_config", discovered.getattr("project_config")?),
            ("local_config", discovered.getattr("local_config")?),
            ("target_name", target),
        ],
    )?
    .getattr("execution_limits")
}

/// Execute the planned SQLBuild phase with the selected target's execution limits.
#[pyfunction]
#[pyo3(signature = (**options))]
fn run_dbt_sqlbuild_work<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(py, "run_dbt_sqlbuild_work", options, OPTIONS)?;
    let request = args.value("request")?;
    let invocation = args.value("invocation")?;
    let compiled = args.value("compiled")?;
    let project = compiled.getattr("project")?;
    let discovered = invocation.getattr("discovered_inputs")?;
    let context = call_with(
        &imported(py, "sqlbuild._native", "DbtSqlbuildWorkContext")?,
        &[
            ("plan_output", args.value("plan_output")?),
            ("connection_config", args.value("connection_config")?),
            ("adapter", compiled.getattr("adapter")?),
            ("adapter_name", compiled.getattr("adapter_name")?),
            ("output_stream", invocation.getattr("output_stream")?),
            ("use_color", request.getattr("use_color")?),
            (
                "snapshots_config",
                discovered.getattr("project_config")?.getattr("snapshots")?,
            ),
            (
                "execution_limits",
                execution_limits(&discovered, project.getattr("effective_target_name")?)?,
            ),
        ],
    )?;
    call_with(
        &imported(py, "sqlbuild._native", "execute_dbt_sqlbuild_work")?,
        &[
            ("context", context),
            ("command", request.getattr("command")?),
            ("project", project),
            ("project_dir", request.getattr("project_dir")?),
            ("fail_fast", request.getattr("fail_fast")?),
            ("verbose", request.getattr("verbose")?),
        ],
    )
}

/// Report a SQLBuild skip transition without writing machine output to stdout.
#[pyfunction]
#[pyo3(signature = (**options))]
fn write_sqlbuild_skip_notice(py: Python<'_>, options: Option<Bound<'_, PyDict>>) -> PyResult<()> {
    let args = KeywordArguments::read(py, "write_sqlbuild_skip_notice", options, OPTIONS)?;
    emit(&args.value("invocation")?.getattr("output_stream")?, "\n")?;
    progress(
        &args.value("request")?.getattr("on_progress")?,
        &args.value("message")?.extract::<String>()?,
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(resolve_dbt_connection_config, module)?)?;
    module.add_function(wrap_pyfunction!(write_dbt_execution_plan_text, module)?)?;
    module.add_function(wrap_pyfunction!(
        execute_dbt_without_state_tracking,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(write_dbt_execution_summary, module)?)?;
    module.add_function(wrap_pyfunction!(
        resolve_sqlbuild_execution_plan_output,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(run_dbt_sqlbuild_work, module)?)?;
    module.add_function(wrap_pyfunction!(write_sqlbuild_skip_notice, module)?)
}
