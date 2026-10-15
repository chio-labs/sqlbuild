//! Public project pipelines for dbt plan, execution and debug.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::dbt_cli::main::dbt_debug_args::dbt_debug_args;
use std::time::Instant;

use crate::bindings::_helpers::build_command::support::{boolean, none, text};
use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::dbt_interop::pipeline_prologue::progress;
use crate::bindings::_helpers::dbt_interop::runtime_config::config_overrides;

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";

const NATIVE_RECORDS: &str = "sqlbuild._native";
const PLAN_OPTIONS: (&[&str], &[&str]) = (
    &["project_dir", "args"],
    &[
        "dbt_runner",
        "dbt_executable",
        "sqlbuild_executable",
        "no_sql_validation",
        "on_progress",
        "progress_stream",
        "use_color",
    ],
);
const DEBUG_OPTIONS: (&[&str], &[&str]) = (
    &["project_dir", "args", "stdout_stream", "stderr_stream"],
    &["dbt_runner", "dbt_executable"],
);

fn native<'py>(
    py: Python<'py>,
    name: &str,
    pairs: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    call_with(&imported(py, "sqlbuild._native", name)?, pairs)
}

fn prepare<'py>(
    request: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let py = request.py();
    let invocation =
        imported(py, "sqlbuild._native", "resolve_dbt_execution_invocation")?.call1((request,))?;
    let manifest = native(
        py,
        "load_compiled_dbt_manifest",
        &[
            ("runner", invocation.getattr("runner")?),
            ("dbt_options", invocation.getattr("dbt_options")?),
            ("full_refresh", boolean(py, false)),
            ("on_progress", request.getattr("on_progress")?),
        ],
    )?;
    let compiled = native(
        py,
        "compile_dbt_interop_project",
        &[
            ("project_dir", request.getattr("project_dir")?),
            (
                "discovered_inputs",
                invocation.getattr("discovered_inputs")?,
            ),
            ("manifest", manifest.clone()),
            ("dbt_vars", invocation.getattr("dbt_vars")?),
            ("no_sql_validation", request.getattr("no_sql_validation")?),
            ("on_progress", request.getattr("on_progress")?),
        ],
    )?;
    Ok((invocation, manifest, compiled))
}

fn resolve_plan<'py>(
    request: &Bound<'py, PyAny>,
    invocation: &Bound<'py, PyAny>,
    compiled: &Bound<'py, PyAny>,
    manifest: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    native(
        request.py(),
        "resolve_dbt_interop_plan",
        &[
            ("command", request.getattr("command")?),
            ("invocation", invocation.clone()),
            ("compiled", compiled.clone()),
            ("manifest", manifest.clone()),
            (
                "sqlbuild_executable",
                request.getattr("sqlbuild_executable")?,
            ),
            ("on_progress", request.getattr("on_progress")?),
        ],
    )
}

/// Execute dbt first and then the SQLBuild work selected by the combined graph.
#[pyfunction]
fn execute_dbt_interop_from_project(request: &Bound<'_, PyAny>) -> PyResult<i64> {
    let py = request.py();
    let command = request.getattr("command")?;
    let kind = imported(py, "sqlbuild._native", "DbtInteropCommand")?;
    if !command.eq(kind.getattr("RUN")?)? && !command.eq(kind.getattr("BUILD")?)? {
        return Err(PyErr::from_value(
            imported(py, "sqlbuild._native", "DbtInteropArgumentError")?.call1((format!(
                "unsupported dbt interop execution command: {}",
                command.str()?
            ),))?,
        ));
    }
    let (invocation, manifest, compiled) = prepare(request)?;
    let resolution = resolve_plan(request, &invocation, &compiled, &manifest)?;
    let plan = resolution.getattr("plan")?;
    let merged = native(
        py,
        "build_merged_dbt_execution_argv",
        &[
            ("command", command),
            ("options", invocation.getattr("dbt_options")?),
            (
                "routed_args",
                invocation.getattr("routed")?.getattr("dbt_args")?,
            ),
            ("plan", plan.clone()),
        ],
    )?;
    native(
        py,
        "write_dbt_execution_plan_text",
        &[
            ("request", request.clone()),
            ("invocation", invocation.clone()),
            ("plan", plan.clone()),
            ("merged_dbt_argv", merged.clone()),
        ],
    )?;
    let execution = native(
        py,
        "execute_dbt_without_state_tracking",
        &[
            ("request", request.clone()),
            ("invocation", invocation.clone()),
            ("merged_dbt_argv", merged),
        ],
    )?;
    native(
        py,
        "write_dbt_execution_summary",
        &[
            ("request", request.clone()),
            ("invocation", invocation.clone()),
            ("execution", execution.clone()),
        ],
    )?;
    let failed = native(
        py,
        "build_failed_sqlbuild_model_names",
        &[
            ("graph", resolution.getattr("graph")?),
            ("manifest", manifest.clone()),
            ("node_results", execution.getattr("node_results")?),
        ],
    )?;
    let code: i64 = execution.getattr("returncode")?.extract()?;
    if code != 0 && !execution.getattr("node_results")?.is_truthy()? {
        return Ok(code);
    }
    let output = native(
        py,
        "resolve_sqlbuild_execution_plan_output",
        &[
            ("request", request.clone()),
            ("invocation", invocation.clone()),
            ("compiled", compiled.clone()),
            ("manifest", manifest),
            ("plan", plan.clone()),
            ("failed_sqlbuild_model_names", failed),
        ],
    )?;
    let skip = if output.is_none() {
        if plan.getattr("sqlbuild_skip_reason")?.is_none() {
            return Ok(code);
        }
        Some("No SQLBuild work selected.")
    } else if !native(py, "plan_has_executable_work", &[("plan", output.clone())])?.is_truthy()? {
        Some("Skipping SQLBuild: no executable work selected.")
    } else {
        None
    };
    if let Some(message) = skip {
        native(
            py,
            "write_sqlbuild_skip_notice",
            &[
                ("request", request.clone()),
                ("invocation", invocation),
                ("message", text(py, message)),
            ],
        )?;
        return Ok(code);
    }
    let connection = native(
        py,
        "resolve_dbt_connection_config",
        &[
            ("request", request.clone()),
            ("invocation", invocation.clone()),
            ("compiled", compiled.clone()),
        ],
    )?;
    let result = native(
        py,
        "run_dbt_sqlbuild_work",
        &[
            ("request", request.clone()),
            ("invocation", invocation),
            ("compiled", compiled),
            ("plan_output", output),
            ("connection_config", connection),
        ],
    )?;
    Ok(code.max(result.extract()?))
}

/// Build an interop plan from actual project files, dbt artifacts and warehouse facts.
#[pyfunction]
#[pyo3(signature = (**options))]
fn plan_dbt_interop_from_project<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(py, "plan_dbt_interop_from_project", options, PLAN_OPTIONS)?;
    let request = call_with(
        &imported(py, NATIVE_RECORDS, "DbtInteropExecutionRequest")?,
        &[
            (
                "command",
                imported(py, "sqlbuild._native", "DbtInteropCommand")?.getattr("PLAN")?,
            ),
            ("project_dir", args.value("project_dir")?),
            ("args", args.value("args")?),
            ("dbt_runner", args.value("dbt_runner")?),
            ("dbt_executable", args.value("dbt_executable")?),
            (
                "sqlbuild_executable",
                if args.passed("sqlbuild_executable")? {
                    args.value("sqlbuild_executable")?
                } else {
                    text(py, "sqb")
                },
            ),
            (
                "no_sql_validation",
                args.value_or_false("no_sql_validation")?,
            ),
            ("on_progress", args.value("on_progress")?),
            ("progress_stream", args.value("progress_stream")?),
            ("use_color", args.value_or_false("use_color")?),
        ],
    )?;
    let (invocation, manifest, compiled) = prepare(&request)?;
    let stream = args.value("progress_stream")?;
    let connection = if stream.is_none() {
        none(py)
    } else {
        native(
            py,
            "ConnectionProgressReporter",
            &[
                ("adapter_name", compiled.getattr("adapter_name")?),
                ("stream", stream),
                ("use_color", args.value_or_false("use_color")?),
            ],
        )?
    };
    let start = Instant::now();
    let resolution = resolve_plan(&request, &invocation, &compiled, &manifest)?;
    let plan = native(
        py,
        "attach_sqlbuild_plan_output",
        &[
            ("plan", resolution.getattr("plan")?),
            ("project_dir", args.value("project_dir")?),
            (
                "discovered_inputs",
                invocation.getattr("discovered_inputs")?,
            ),
            ("compiled", compiled),
            (
                "sqlbuild_args",
                invocation.getattr("effective_sqlbuild_args")?,
            ),
            ("connection_progress", connection),
            ("on_progress", args.value("on_progress")?),
        ],
    )?;
    progress(
        &args.value("on_progress")?,
        &format!(
            "Generated dbt interop plan. ({:.2}s)",
            start.elapsed().as_secs_f64()
        ),
    )?;
    Ok(plan)
}

/// Run dbt debug using SQLBuild's resolved dbt configuration.
#[pyfunction]
#[pyo3(signature = (**options))]
fn debug_dbt_from_project(py: Python<'_>, options: Option<Bound<'_, PyDict>>) -> PyResult<i64> {
    let args = KeywordArguments::read(py, "debug_dbt_from_project", options, DEBUG_OPTIONS)?;
    let discovered = native(
        py,
        "discover_project_inputs",
        &[("project_dir", args.value("project_dir")?)],
    )?;
    let dbt_args: Vec<String> = args
        .value("args")?
        .try_iter()?
        .map(|arg| arg?.extract())
        .collect::<PyResult<_>>()?;
    let overrides = config_overrides(py, &dbt_args)?;
    let resolved = native(
        py,
        "resolve_dbt_config",
        &[
            ("project_root", args.value("project_dir")?),
            (
                "config",
                discovered.getattr("project_config")?.getattr("dbt")?,
            ),
            (
                "local_config",
                discovered.getattr("local_config")?.getattr("dbt")?,
            ),
            ("overrides", overrides),
            ("require_project_dir", boolean(py, true)),
        ],
    )?;
    let dbt_options = call_with(
        &imported(py, NATIVE_RECORDS_MODULE, "DbtCliOptions")?,
        &[
            ("project_dir", resolved.getattr("project_dir")?),
            ("profiles_dir", resolved.getattr("profiles_dir")?),
            ("target", resolved.getattr("target")?),
        ],
    )?;
    let mut runner = args.value("dbt_runner")?;
    if !runner.is_truthy()? {
        runner = call_with(
            &imported(py, "sqlbuild._native", "DbtRunner")?,
            &[("dbt_executable", args.value("dbt_executable")?)],
        )?;
    }
    let argv: Vec<String> = args.value("args")?.extract()?;
    let result = call_with(
        &runner.getattr("debug")?,
        &[
            ("options", dbt_options),
            ("args", PyTuple::new(py, dbt_debug_args(&argv))?.into_any()),
        ],
    )?;
    let stdout = args.value("stdout_stream")?;
    let stderr = args.value("stderr_stream")?;
    stdout.call_method1("write", (result.getattr("stdout")?,))?;
    stderr.call_method1("write", (result.getattr("stderr")?,))?;
    stdout.call_method0("flush")?;
    stderr.call_method0("flush")?;
    result.getattr("returncode")?.extract()
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(execute_dbt_interop_from_project, module)?)?;
    module.add_function(wrap_pyfunction!(plan_dbt_interop_from_project, module)?)?;
    module.add_function(wrap_pyfunction!(debug_dbt_from_project, module)?)
}
