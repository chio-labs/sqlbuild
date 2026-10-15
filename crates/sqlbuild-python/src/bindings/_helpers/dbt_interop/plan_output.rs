//! Plan selected SQLBuild work against the live adapter and attach it to the interop plan.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::build_command::support::{boolean, keyword_relay, none};
use crate::bindings::_helpers::command_runtime::connection::{
    anchor_duckdb_database, with_dbt_profile,
};
use crate::bindings::_helpers::compile_driver::plan_result::connection_with_hooks;
use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported, keywords,
};

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";

const NATIVE_RECORDS: &str = "sqlbuild._native";
const PLANNER_MODELS: &str = "sqlbuild._native";
const HOOKS: &str = "sqlbuild.runtime.contracts.models";
const BUILD_OPTIONS: (&[&str], &[&str]) = (&["environment", "request", "hooks"], &[]);
const ATTACH_OPTIONS: (&[&str], &[&str]) = (
    &[
        "plan",
        "project_dir",
        "discovered_inputs",
        "compiled",
        "sqlbuild_args",
        "connection_progress",
        "on_progress",
    ],
    &[],
);

pub(crate) fn connection_config<'py>(
    environment: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = environment.py();
    let discovered = environment.getattr("discovered_inputs")?;
    let raw = call_with(
        &imported(py, "sqlbuild._native", "build_effective_connection_config")?,
        &[("discovered_inputs", discovered.clone())],
    )?;
    let raw: Bound<'_, PyDict> = raw.cast_into()?;
    let project_dir = environment.getattr("project_dir")?;
    let adapter_name = environment.getattr("adapter_name")?;
    let config: Bound<'_, PyDict> = with_dbt_profile(
        &raw,
        raw.copy()?,
        (&project_dir, &adapter_name),
        (&discovered, &py.None().into_bound(py)),
    )?;
    anchor_duckdb_database(
        &config,
        (&project_dir, &adapter_name.str()?.extract::<String>()?),
    )?;
    let config = config.into_any();
    call_with(
        &imported(py, "sqlbuild._native", "apply_command_warehouse")?,
        &[
            ("config", config),
            ("adapter_name", environment.getattr("adapter_name")?),
            ("discovered_inputs", discovered),
            ("project_dir", environment.getattr("project_dir")?),
            ("selected_target", none(py)),
        ],
    )
}

fn flag_value<'py>(args: &Bound<'py, PyAny>, flag: &str) -> PyResult<Bound<'py, PyAny>> {
    if !args.contains(flag)? {
        return Ok(none(args.py()));
    }
    let index: usize = args.call_method1("index", (flag,))?.extract()?;
    if index + 1 < args.len()? {
        args.get_item(index + 1)
    } else {
        Ok(none(args.py()))
    }
}

pub(crate) fn connection_hooks<'py>(
    reporter: &Bound<'py, PyAny>,
    callback: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = reporter.py();
    let mut pairs = vec![("on_progress", callback)];
    if !reporter.is_none() {
        pairs.push((
            "on_connection_start",
            reporter.getattr("on_connection_start")?,
        ));
        for name in ["on_connection_complete", "on_connection_error"] {
            pairs.push((
                name,
                keyword_relay(
                    reporter.getattr(name)?,
                    &["connection_count", "elapsed_seconds"],
                )?,
            ));
        }
    }
    call_with(&imported(py, HOOKS, "ConnectionHooks")?, &pairs)
}

/// Open through the shared adapter boundary while retaining keyword-only timing callbacks.
fn open_connection<'py>(
    environment: &Bound<'py, PyAny>,
    config: Bound<'py, PyAny>,
    hooks: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = environment.py();
    let mut pairs = vec![("on_connection_start", hooks.getattr("on_connection_start")?)];
    for name in ["on_connection_complete", "on_connection_error"] {
        let callback = hooks.getattr(name)?;
        pairs.push((
            name,
            if callback.is_none() {
                callback
            } else {
                keyword_relay(callback, &["connection_count", "elapsed_seconds"])?
            },
        ));
    }
    let relayed = call_with(&imported(py, HOOKS, "ConnectionHooks")?, &pairs)?;
    connection_with_hooks(&environment.getattr("adapter")?, &config, &relayed)
}

/// Build the SQLBuild plan from current warehouse facts, closing the custom adapter connection.
#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn build_sqlbuild_plan_output<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments =
        KeywordArguments::read(py, "build_sqlbuild_plan_output", options, BUILD_OPTIONS)?;
    let request = arguments.value("request")?;
    let selected = request.getattr("selected_model_names")?;
    if !selected.is_truthy()? {
        return Ok(none(py));
    }
    let environment = arguments.value("environment")?;
    let hooks = arguments.value("hooks")?;
    let connection = open_connection(&environment, connection_config(&environment)?, &hooks)?;
    let planned = (|| {
        let args = request.getattr("sqlbuild_args")?;
        let deferral = call_with(
            &imported(py, "sqlbuild._native", "resolve_model_deferral_inputs")?,
            &[
                ("project", environment.getattr("project")?),
                (
                    "discovered_inputs",
                    environment.getattr("discovered_inputs")?,
                ),
                ("adapter", environment.getattr("adapter")?),
                ("connection", connection.clone()),
                ("defer_to", flag_value(&args, "--defer-to")?),
            ],
        )?;
        let cursor = call_with(
            &imported(py, PLANNER_MODELS, "CursorOverrides")?,
            &[
                ("start_ts", flag_value(&args, "--start-cursor-ts")?),
                ("end_ts", flag_value(&args, "--end-cursor-ts")?),
                ("start_int", flag_value(&args, "--start-cursor-int")?),
                ("end_int", flag_value(&args, "--end-cursor-int")?),
            ],
        )?;
        let full_refresh = boolean(py, args.contains("--full-refresh")?);
        let selection = call_with(
            &imported(py, NATIVE_RECORDS_MODULE, "PlannerSelection")?,
            &[("select", selected.clone())],
        )?;
        let overrides = call_with(
            &imported(py, NATIVE_RECORDS_MODULE, "PlannerOverrides")?,
            &[
                ("cursor_overrides", cursor),
                ("full_refresh", full_refresh.clone()),
                (
                    "external_blocked_model_names",
                    request.getattr("external_blocked_model_names")?,
                ),
            ],
        )?;
        let discovered = environment.getattr("discovered_inputs")?;
        let result = call_with(
            &imported(py, "sqlbuild._native", "build_execution_plan")?,
            &[
                ("project", environment.getattr("project")?),
                ("adapter", environment.getattr("adapter")?),
                ("connection", connection.clone()),
                ("selection", selection),
                ("overrides", overrides),
                ("deferral", deferral),
                (
                    "policies",
                    imported(py, NATIVE_RECORDS_MODULE, "PlannerPolicies")?.call0()?,
                ),
                ("on_progress", hooks.getattr("on_progress")?),
                ("project_config", discovered.getattr("project_config")?),
                ("local_config", discovered.getattr("local_config")?),
            ],
        );
        match result {
            Err(error)
                if error
                    .is_instance(py, &imported(py, "sqlbuild._native", "PlannerInputError")?) =>
            {
                call_with(
                    &imported(py, "sqlbuild._native", "build_display_only_sqlbuild_plan")?,
                    &[
                        ("project", environment.getattr("project")?),
                        ("selected_model_names", selected),
                        ("full_refresh", full_refresh),
                    ],
                )
            }
            result => result,
        }
    })();
    environment
        .getattr("adapter")?
        .call_method1("close", (connection,))?;
    planned
}

/// Attach live SQLBuild planning when the selection contains SQLBuild models.
#[pyfunction]
#[pyo3(signature = (**options))]
fn attach_sqlbuild_plan_output<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(py, "attach_sqlbuild_plan_output", options, ATTACH_OPTIONS)?;
    let compiled = args.value("compiled")?;
    let plan = args.value("plan")?;
    let environment = call_with(
        &imported(py, NATIVE_RECORDS, "DbtPlanEnvironment")?,
        &[
            ("project_dir", args.value("project_dir")?),
            ("discovered_inputs", args.value("discovered_inputs")?),
            ("project", compiled.getattr("project")?),
            ("adapter", compiled.getattr("adapter")?),
            ("adapter_name", compiled.getattr("adapter_name")?),
        ],
    )?;
    let request = call_with(
        &imported(py, NATIVE_RECORDS, "DbtSqlbuildPlanRequest")?,
        &[
            (
                "selected_model_names",
                plan.getattr("selection")?.getattr("sqlbuild_model_names")?,
            ),
            ("sqlbuild_args", args.value("sqlbuild_args")?),
        ],
    )?;
    let output = build_sqlbuild_plan_output(
        py,
        Some(keywords(
            py,
            &[
                ("environment", environment),
                ("request", request),
                (
                    "hooks",
                    connection_hooks(
                        &args.value("connection_progress")?,
                        args.value("on_progress")?,
                    )?,
                ),
            ],
        )?),
    )?;
    if output.is_none() {
        return Ok(plan);
    }
    imported(py, "dataclasses", "replace")?.call(
        (plan,),
        Some(&keywords(py, &[("sqlbuild_plan_output", output)])?),
    )
}

/// Prefer stderr for dbt subprocess failure details, retaining Python whitespace semantics.
#[pyfunction]
fn dbt_failure_detail<'py>(result: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let stderr = result.getattr("stderr")?;
    let detail = if stderr.is_truthy()? {
        stderr
    } else {
        result.getattr("stdout")?
    }
    .call_method0("strip")?;
    if detail.is_truthy()? {
        Ok(detail)
    } else {
        Ok(none(result.py()))
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_sqlbuild_plan_output, module)?)?;
    module.add_function(wrap_pyfunction!(attach_sqlbuild_plan_output, module)?)?;
    module.add_function(wrap_pyfunction!(dbt_failure_detail, module)?)
}
