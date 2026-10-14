//! Discover, compile and resolve the combined dbt pipeline through its existing boundaries.

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::PyDict;
use pyo3::{pyfunction, wrap_pyfunction};
use std::time::Instant;

const MODELS: &str = "sqlbuild.integrations.dbt.models";
const COMPILE_OPTIONS: (&[&str], &[&str]) = (
    &[
        "project_dir",
        "discovered_inputs",
        "manifest",
        "dbt_vars",
        "no_sql_validation",
        "on_progress",
    ],
    &[],
);
const MANIFEST_OPTIONS: (&[&str], &[&str]) = (
    &["runner", "dbt_options", "full_refresh", "on_progress"],
    &[],
);
const PLAN_OPTIONS: (&[&str], &[&str]) = (
    &[
        "command",
        "invocation",
        "compiled",
        "manifest",
        "sqlbuild_executable",
        "on_progress",
    ],
    &[],
);

pub(crate) fn progress(callback: &Bound<'_, PyAny>, message: &str) -> PyResult<()> {
    if !callback.is_none() {
        callback.call1((message,))?;
    }
    Ok(())
}

fn completed(callback: &Bound<'_, PyAny>, message: &str, start: Instant) -> PyResult<()> {
    progress(
        callback,
        &format!("{message} ({:.2}s)", start.elapsed().as_secs_f64()),
    )
}

/// Resolve the execution invocation without invoking dbt or SQLBuild work.
#[pyfunction]
pub(crate) fn resolve_dbt_execution_invocation<'py>(
    request: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = request.py();
    let mut executable = request.getattr("dbt_executable")?;
    if !executable.is_truthy()? {
        executable = imported(py, "sqlbuild._native", "resolve_dbt_executable")?.call0()?;
    }
    let mut stream = request.getattr("progress_stream")?;
    if !stream.is_truthy()? {
        stream = py.import("sys")?.getattr("stdout")?;
    }
    let parsed = call_with(
        &imported(
            py,
            "sqlbuild.integrations.dbt.main.cli._parse_execution_args",
            "parse_dbt_execution_args",
        )?,
        &[
            ("command", request.getattr("command")?),
            ("args", request.getattr("args")?),
        ],
    )?;
    let routed = call_with(
        &imported(py, "sqlbuild._native", "route_dbt_interop_args")?,
        &[("command", request.getattr("command")?), ("parsed", parsed)],
    )?;
    let discovered = call_with(
        &imported(py, "sqlbuild._native", "discover_project_inputs")?,
        &[("project_dir", request.getattr("project_dir")?)],
    )?;
    let options = call_with(
        &imported(
            py,
            "sqlbuild.integrations.dbt.main.config._resolve_plan_options",
            "resolve_dbt_plan_options",
        )?,
        &[
            ("project_dir", request.getattr("project_dir")?),
            ("discovered_inputs", discovered.clone()),
            ("dbt_args", routed.getattr("dbt_args")?),
        ],
    )?;
    let vars = call_with(
        &imported(
            py,
            "sqlbuild.integrations.dbt.main.config._resolve_vars_mapping",
            "resolve_dbt_vars_mapping",
        )?,
        &[
            (
                "project_config",
                discovered.getattr("project_config")?.getattr("dbt")?,
            ),
            (
                "local_config",
                discovered.getattr("local_config")?.getattr("dbt")?,
            ),
            ("dbt_args", routed.getattr("dbt_args")?),
        ],
    )?;
    let mut runner = request.getattr("dbt_runner")?;
    if !runner.is_truthy()? {
        runner = call_with(
            &imported(
                py,
                "sqlbuild.integrations.dbt.classes.dbt_runner",
                "DbtRunner",
            )?,
            &[("dbt_executable", executable.clone())],
        )?;
    }
    let dbt_stream = request.getattr("dbt_stdout_stream")?;
    call_with(
        &imported(py, MODELS, "DbtInteropInvocation")?,
        &[
            ("dbt_executable", executable),
            ("output_stream", stream.clone()),
            (
                "dbt_output_stream",
                if dbt_stream.is_truthy()? {
                    dbt_stream
                } else {
                    stream
                },
            ),
            ("effective_sqlbuild_args", routed.getattr("sqlbuild_args")?),
            ("routed", routed),
            ("discovered_inputs", discovered),
            ("dbt_options", options),
            ("dbt_vars", vars),
            ("runner", runner),
        ],
    )
}

/// Compile dbt and load the manifest after a successful subprocess result.
#[pyfunction]
#[pyo3(signature = (**options))]
fn load_compiled_dbt_manifest<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(py, "load_compiled_dbt_manifest", options, MANIFEST_OPTIONS)?;
    let callback = args.value("on_progress")?;
    let start = Instant::now();
    progress(&callback, "Compiling dbt project...")?;
    let result = call_with(
        &args.value("runner")?.getattr("compile")?,
        &[
            ("options", args.value("dbt_options")?),
            ("full_refresh", args.value("full_refresh")?),
        ],
    )?;
    if result.getattr("returncode")?.extract::<i64>()? != 0 {
        let detail = imported(py, "sqlbuild._native", "dbt_failure_detail")?.call1((result,))?;
        let error = imported(
            py,
            "sqlbuild.integrations.dbt.exceptions",
            "DbtInteropRuntimeError",
        )?
        .call(
            ("dbt compile failed",),
            Some(
                &crate::bindings::_helpers::compile_driver::python_calls::keywords(
                    py,
                    &[("help", detail)],
                )?,
            ),
        )?;
        return Err(PyErr::from_value(error));
    }
    completed(&callback, "Compiled dbt project.", start)?;
    let start = Instant::now();
    progress(&callback, "Loading dbt manifest...")?;
    let path = call_with(
        &imported(
            py,
            "sqlbuild.integrations.dbt.main.manifest._resolve_manifest_path",
            "resolve_dbt_manifest_path",
        )?,
        &[("options", args.value("dbt_options")?)],
    )?;
    let manifest = call_with(
        &imported(py, "sqlbuild._native", "load_dbt_manifest_index")?,
        &[("manifest_path", path)],
    )?;
    completed(&callback, "Loaded dbt manifest.", start)?;
    Ok(manifest)
}

/// Compile SQLBuild models against dbt references using the existing adapter boundary.
#[pyfunction]
#[pyo3(signature = (**options))]
fn compile_dbt_interop_project<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(py, "compile_dbt_interop_project", options, COMPILE_OPTIONS)?;
    let callback = args.value("on_progress")?;
    let start = Instant::now();
    progress(&callback, "Compiling SQLBuild project...")?;
    let discovered = args.value("discovered_inputs")?;
    let name = call_with(
        &imported(py, "sqlbuild._native", "resolve_effective_adapter_name")?,
        &[
            ("project_config", discovered.getattr("project_config")?),
            ("local_config", discovered.getattr("local_config")?),
        ],
    )?;
    let adapter = call_with(
        &imported(
            py,
            "sqlbuild.integrations.dbt.main.runtime._resolve_interop_adapter",
            "resolve_dbt_interop_adapter",
        )?,
        &[
            ("adapter_name", name.clone()),
            ("project_dir", args.value("project_dir")?),
        ],
    )?;
    let resolver = call_with(
        &imported(
            py,
            "sqlbuild.integrations.dbt.classes.dbt_compile_reference_resolver",
            "DbtCompileReferenceResolver",
        )?,
        &[("dbt_manifest", args.value("manifest")?)],
    )?;
    let project = call_with(
        &imported(py, "sqlbuild._native", "build_compiled_project")?,
        &[
            ("discovered_inputs", discovered),
            ("adapter", adapter.clone()),
            ("no_sql_validation", args.value("no_sql_validation")?),
            ("cli_vars", args.value("dbt_vars")?),
            ("external_sql_reference_resolver", resolver),
        ],
    )?;
    completed(&callback, "Compiled SQLBuild project.", start)?;
    call_with(
        &imported(py, MODELS, "DbtInteropCompiledProject")?,
        &[
            ("adapter_name", name),
            ("adapter", adapter),
            ("project", project),
        ],
    )
}

/// Build the combined graph and resolve its dbt and SQLBuild selections.
#[pyfunction]
#[pyo3(signature = (**options))]
fn resolve_dbt_interop_plan<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(py, "resolve_dbt_interop_plan", options, PLAN_OPTIONS)?;
    let callback = args.value("on_progress")?;
    let start = Instant::now();
    progress(&callback, "Building dbt interop graph...")?;
    let project = args.value("compiled")?.getattr("project")?;
    let graph = call_with(
        &imported(py, "sqlbuild._native", "build_dbt_combined_graph")?,
        &[
            ("manifest", args.value("manifest")?),
            ("project", project.clone()),
        ],
    )?;
    completed(&callback, "Built dbt interop graph.", start)?;
    let start = Instant::now();
    progress(&callback, "Resolving dbt and SQLBuild selection...")?;
    let invocation = args.value("invocation")?;
    let routed = invocation.getattr("routed")?;
    let tuple = py.import("builtins")?.getattr("tuple")?;
    let command_args = call_with(
        &imported(py, MODELS, "DbtInteropCommandArgs")?,
        &[
            ("select", tuple.call1((routed.getattr("select")?,))?),
            ("exclude", tuple.call1((routed.getattr("exclude")?,))?),
            (
                "dbt_command_args",
                tuple.call1((routed.getattr("dbt_args")?,))?,
            ),
            (
                "sqlbuild_command_args",
                tuple.call1((invocation.getattr("effective_sqlbuild_args")?,))?,
            ),
            ("dbt_executable", invocation.getattr("dbt_executable")?),
            ("sqlbuild_executable", args.value("sqlbuild_executable")?),
        ],
    )?;
    let plan = call_with(
        &imported(py, "sqlbuild._native", "plan_dbt_interop_command")?,
        &[
            ("command", args.value("command")?),
            ("project", project),
            ("manifest", args.value("manifest")?),
            ("graph", graph.clone()),
            ("dbt_runner", invocation.getattr("runner")?),
            ("dbt_options", invocation.getattr("dbt_options")?),
            ("command_args", command_args),
        ],
    )?;
    completed(&callback, "Resolved dbt and SQLBuild selection.", start)?;
    call_with(
        &imported(py, MODELS, "DbtInteropPlanResolution")?,
        &[("graph", graph), ("plan", plan)],
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(resolve_dbt_execution_invocation, module)?)?;
    module.add_function(wrap_pyfunction!(load_compiled_dbt_manifest, module)?)?;
    module.add_function(wrap_pyfunction!(compile_dbt_interop_project, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_dbt_interop_plan, module)?)
}
