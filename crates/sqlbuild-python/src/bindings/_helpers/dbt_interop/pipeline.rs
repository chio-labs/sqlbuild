//! Public project pipelines for dbt plan, execution and debug.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::dbt_cli::main::dbt_debug_args::dbt_debug_args;
use std::time::Instant;

use crate::bindings::_helpers::build_command::support::{boolean, none, text};
use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, call_with};
use crate::bindings::_helpers::dbt_interop::pipeline_prologue::progress;
use crate::bindings::_helpers::dbt_interop::runtime_config::config_overrides;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::ids::{ErrorId, NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;

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
    name: NativeAttr,
    pairs: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    call_with(&registry::native(py, name)?, pairs)
}

fn prepare<'py>(
    request: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let py = request.py();
    let invocation =
        registry::native(py, NativeAttr::ResolveDbtExecutionInvocation)?.call1((request,))?;
    let manifest = native(
        py,
        NativeAttr::LoadCompiledDbtManifest,
        &[
            ("runner", native_field(&invocation, "runner")?),
            ("dbt_options", native_field(&invocation, "dbt_options")?),
            ("full_refresh", boolean(py, false)),
            ("on_progress", native_field(request, "on_progress")?),
        ],
    )?;
    let compiled = native(
        py,
        NativeAttr::CompileDbtInteropProject,
        &[
            ("project_dir", native_field(request, "project_dir")?),
            (
                "discovered_inputs",
                native_field(&invocation, "discovered_inputs")?,
            ),
            ("manifest", manifest.clone()),
            ("dbt_vars", native_field(&invocation, "dbt_vars")?),
            (
                "no_sql_validation",
                native_field(request, "no_sql_validation")?,
            ),
            ("on_progress", native_field(request, "on_progress")?),
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
        NativeAttr::ResolveDbtInteropPlan,
        &[
            ("command", native_field(request, "command")?),
            ("invocation", invocation.clone()),
            ("compiled", compiled.clone()),
            ("manifest", manifest.clone()),
            (
                "sqlbuild_executable",
                native_field(request, "sqlbuild_executable")?,
            ),
            ("on_progress", native_field(request, "on_progress")?),
        ],
    )
}

/// Execute dbt first and then the SQLBuild work selected by the combined graph.
#[pyfunction]
fn execute_dbt_interop_from_project(request: &Bound<'_, PyAny>) -> PyResult<i64> {
    let py = request.py();
    let command = native_field(request, "command")?;
    let kind = registry::class(py, RecordId::DbtInteropCommand)?;
    if !command.eq(native_field(&kind, "RUN")?)? && !command.eq(native_field(&kind, "BUILD")?)? {
        return Err(PyErr::from_value(
            registry::error(py, ErrorId::DbtInteropArgument)?.call1((format!(
                "unsupported dbt interop execution command: {}",
                command.str()?
            ),))?,
        ));
    }
    let (invocation, manifest, compiled) = prepare(request)?;
    let resolution = resolve_plan(request, &invocation, &compiled, &manifest)?;
    let plan = native_field(&resolution, "plan")?;
    let merged = native(
        py,
        NativeAttr::BuildMergedDbtExecutionArgv,
        &[
            ("command", command),
            ("options", native_field(&invocation, "dbt_options")?),
            (
                "routed_args",
                native_field(&invocation, "routed")?.getattr("dbt_args")?,
            ),
            ("plan", plan.clone()),
        ],
    )?;
    native(
        py,
        NativeAttr::WriteDbtExecutionPlanText,
        &[
            ("request", request.clone()),
            ("invocation", invocation.clone()),
            ("plan", plan.clone()),
            ("merged_dbt_argv", merged.clone()),
        ],
    )?;
    let execution = native(
        py,
        NativeAttr::ExecuteDbtWithoutStateTracking,
        &[
            ("request", request.clone()),
            ("invocation", invocation.clone()),
            ("merged_dbt_argv", merged),
        ],
    )?;
    native(
        py,
        NativeAttr::WriteDbtExecutionSummary,
        &[
            ("request", request.clone()),
            ("invocation", invocation.clone()),
            ("execution", execution.clone()),
        ],
    )?;
    let failed = native(
        py,
        NativeAttr::BuildFailedSqlbuildModelNames,
        &[
            ("graph", native_field(&resolution, "graph")?),
            ("manifest", manifest.clone()),
            ("node_results", native_field(&execution, "node_results")?),
        ],
    )?;
    let code: i64 = native_field(&execution, "returncode")?.extract()?;
    if code != 0 && !native_field(&execution, "node_results")?.is_truthy()? {
        return Ok(code);
    }
    let output = native(
        py,
        NativeAttr::ResolveSqlbuildExecutionPlanOutput,
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
        if native_field(&plan, "sqlbuild_skip_reason")?.is_none() {
            return Ok(code);
        }
        Some("No SQLBuild work selected.")
    } else if !native(
        py,
        NativeAttr::PlanHasExecutableWork,
        &[("plan", output.clone())],
    )?
    .is_truthy()?
    {
        Some("Skipping SQLBuild: no executable work selected.")
    } else {
        None
    };
    if let Some(message) = skip {
        native(
            py,
            NativeAttr::WriteSqlbuildSkipNotice,
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
        NativeAttr::ResolveDbtConnectionConfig,
        &[
            ("request", request.clone()),
            ("invocation", invocation.clone()),
            ("compiled", compiled.clone()),
        ],
    )?;
    let result = native(
        py,
        NativeAttr::RunDbtSqlbuildWork,
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
        &registry::class(py, RecordId::DbtInteropExecutionRequest)?,
        &[
            (
                "command",
                registry::class(py, RecordId::DbtInteropCommand)?.getattr("PLAN")?,
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
            NativeAttr::ConnectionProgressReporter,
            &[
                ("adapter_name", native_field(&compiled, "adapter_name")?),
                ("stream", stream),
                ("use_color", args.value_or_false("use_color")?),
            ],
        )?
    };
    let start = Instant::now();
    let resolution = resolve_plan(&request, &invocation, &compiled, &manifest)?;
    let plan = native(
        py,
        NativeAttr::AttachSqlbuildPlanOutput,
        &[
            ("plan", native_field(&resolution, "plan")?),
            ("project_dir", args.value("project_dir")?),
            (
                "discovered_inputs",
                native_field(&invocation, "discovered_inputs")?,
            ),
            ("compiled", compiled),
            (
                "sqlbuild_args",
                native_field(&invocation, "effective_sqlbuild_args")?,
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
        NativeAttr::DiscoverProjectInputs,
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
        NativeAttr::ResolveDbtConfig,
        &[
            ("project_root", args.value("project_dir")?),
            (
                "config",
                native_field(&discovered, "project_config")?.getattr("dbt")?,
            ),
            (
                "local_config",
                native_field(&discovered, "local_config")?.getattr("dbt")?,
            ),
            ("overrides", overrides),
            ("require_project_dir", boolean(py, true)),
        ],
    )?;
    let dbt_options = call_with(
        &registry::class(py, RecordId::DbtCliOptions)?,
        &[
            ("project_dir", native_field(&resolved, "project_dir")?),
            ("profiles_dir", native_field(&resolved, "profiles_dir")?),
            ("target", native_field(&resolved, "target")?),
        ],
    )?;
    let mut runner = args.value("dbt_runner")?;
    if !runner.is_truthy()? {
        runner = call_with(
            &registry::native(py, NativeAttr::DbtRunner)?,
            &[("dbt_executable", args.value("dbt_executable")?)],
        )?;
    }
    let argv: Vec<String> = args.value("args")?.extract()?;
    let result = call_with(
        &native_field(&runner, "debug")?,
        &[
            ("options", dbt_options),
            ("args", PyTuple::new(py, dbt_debug_args(&argv))?.into_any()),
        ],
    )?;
    let stdout = args.value("stdout_stream")?;
    let stderr = args.value("stderr_stream")?;
    stdout.call_method1("write", (native_field(&result, "stdout")?,))?;
    stderr.call_method1("write", (native_field(&result, "stderr")?,))?;
    stdout.call_method0("flush")?;
    stderr.call_method0("flush")?;
    native_field(&result, "returncode")?.extract()
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(execute_dbt_interop_from_project, module)?)?;
    module.add_function(wrap_pyfunction!(plan_dbt_interop_from_project, module)?)?;
    module.add_function(wrap_pyfunction!(debug_dbt_from_project, module)?)
}
