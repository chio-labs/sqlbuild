//! Enforce interop plan safety before entering the Python build executor.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::PyDict;
use pyo3::{IntoPyObjectExt, pyfunction, wrap_pyfunction};
use sqlbuild_core::build_command::constants::{
    EXECUTION_LIMIT_DBT_NOTE, MISSING_ORIGIN_DBT_HELP, RETENTION_DECREASE_DBT_HELP,
    SNAPSHOT_FULL_REFRESH_DBT_HELP, TABLE_TYPE_DOWNGRADE_DBT_HELP,
};

use crate::bindings::_helpers::build_command::support::{
    boolean, emit, joined, keyword_relay, none, text, tuple,
};
use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, call_with};
use crate::bindings::_helpers::native_host::executor::ExecutorHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::records::construct::{new_record_with, record_class};
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;

const WORK_OPTIONS: (&[&str], &[&str]) = (
    &[
        "context",
        "command",
        "project",
        "project_dir",
        "fail_fast",
        "verbose",
    ],
    &[],
);

/// Interop has no allow flags; destructive work uses the ordinary interactive safety gates.
#[pyfunction]
fn dbt_interop_plan_safety_gates(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    new_record_with(
        py,
        RecordId::PlanSafetyGates,
        &[
            ("allow_missing_migration_origin", boolean(py, false)),
            ("allow_snapshot_full_refresh", boolean(py, false)),
            ("allow_table_type_downgrade", boolean(py, false)),
            ("allow_retention_decrease", boolean(py, false)),
            (
                "missing_origin_help",
                MISSING_ORIGIN_DBT_HELP.into_bound_py_any(py)?,
            ),
            (
                "snapshot_full_refresh_help",
                SNAPSHOT_FULL_REFRESH_DBT_HELP.into_bound_py_any(py)?,
            ),
            (
                "table_type_downgrade_help",
                TABLE_TYPE_DOWNGRADE_DBT_HELP.into_bound_py_any(py)?,
            ),
            (
                "retention_decrease_help",
                RETENTION_DECREASE_DBT_HELP.into_bound_py_any(py)?,
            ),
            (
                "execution_limit_note",
                EXECUTION_LIMIT_DBT_NOTE.into_bound_py_any(py)?,
            ),
        ],
    )
}

/// Execute SQLBuild work only after its plan safety policies succeed.
#[pyfunction]
#[pyo3(signature = (**options))]
fn execute_dbt_sqlbuild_work<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<i64> {
    let args = KeywordArguments::read(py, "execute_dbt_sqlbuild_work", options, WORK_OPTIONS)?;
    let context = args.value("context")?;
    let project = args.value("project")?;
    let plan = native_field(&context, "plan_output")?;
    let output = native_field(&context, "output_stream")?;
    let color = native_field(&context, "use_color")?;
    call_with(
        &registry::native(py, NativeAttr::EnforcePlanSafetyPolicies)?,
        &[
            ("plan", plan.clone()),
            ("gates", dbt_interop_plan_safety_gates(py)?),
            (
                "snapshots_config",
                native_field(&context, "snapshots_config")?,
            ),
            (
                "target_name",
                native_field(&project, "effective_target_name")?,
            ),
            (
                "execution_limits",
                native_field(&context, "execution_limits")?,
            ),
            (
                "streams",
                tuple(py, &[py.import("sys")?.getattr("stdin")?, output.clone()])?,
            ),
        ],
    )?;
    let callbacks = call_with(
        &registry::native(py, NativeAttr::BuildProgressCallbacks)?,
        &[
            ("plan", plan.clone()),
            ("use_color", color.clone()),
            ("verbose", args.value("verbose")?),
            ("debug", boolean(py, false)),
        ],
    )?;
    let command = args.value("command")?;
    let kinds = record_class(py, RecordId::DbtInteropCommand)?;
    let display = if command.eq(native_field(&kinds, "RUN")?)? {
        "sqb build --no-tests --no-audits".to_owned()
    } else {
        format!(
            "sqb {}",
            native_field(&command, "value")?.extract::<String>()?
        )
    };
    let concurrency = native_field(&project, "settings")?.getattr("concurrency")?;
    let header = call_with(
        &registry::native(py, NativeAttr::FormatExecutionHeader)?,
        &[
            ("command", text(py, &display)),
            ("target", none(py)),
            ("concurrency", concurrency.clone()),
        ],
    )?;
    let style = call_with(
        &registry::native(py, NativeAttr::CliStyle)?,
        &[("use_color", color.clone())],
    )?;
    emit(
        &output,
        &format!(
            "{}  {}\n\n",
            style
                .call_method1("object_name", ("SQLBuild execution",))?
                .extract::<String>()?,
            style
                .call_method1("muted", (header,))?
                .extract::<String>()?
        ),
    )?;
    let connection = call_with(
        &registry::native(py, NativeAttr::ConnectionProgressReporter)?,
        &[
            ("adapter_name", native_field(&context, "adapter_name")?),
            ("stream", output.clone()),
            ("blank_line_after_complete", boolean(py, true)),
            ("use_color", color.clone()),
        ],
    )?;
    let build = command.eq(native_field(&kinds, "BUILD")?)?;
    let runtime = call_with(
        &host::entry(py, ExecutorHost::BuildRuntimeParams)?,
        &[
            ("run_id", native_field(&project, "run_id")?),
            ("run_tests", boolean(py, build)),
            ("run_audits", boolean(py, build)),
            ("fail_fast", args.value("fail_fast")?),
            ("max_concurrency", concurrency),
            ("use_color", color.clone()),
        ],
    )?;
    let hooks = call_with(
        &host::entry(py, ExecutorHost::BuildCallbacks)?,
        &[
            (
                "on_node_start",
                keyword_relay(
                    native_field(&callbacks, "on_node_start")?,
                    &["name", "resource_kind"],
                )?,
            ),
            (
                "on_node_complete",
                native_field(&callbacks, "on_node_complete")?,
            ),
            (
                "on_sub_progress",
                native_field(&callbacks, "on_sub_progress")?,
            ),
            (
                "on_connection_start",
                native_field(&connection, "on_connection_start")?,
            ),
            (
                "on_connection_complete",
                keyword_relay(
                    native_field(&connection, "on_connection_complete")?,
                    &["connection_count", "elapsed_seconds"],
                )?,
            ),
            (
                "on_connection_error",
                keyword_relay(
                    native_field(&connection, "on_connection_error")?,
                    &["connection_count", "elapsed_seconds"],
                )?,
            ),
        ],
    )?;
    let result = call_with(
        &host::entry(py, ExecutorHost::RunBuildPipeline)?,
        &[
            ("plan", plan.clone()),
            (
                "connection_config",
                native_field(&context, "connection_config")?,
            ),
            ("adapter", native_field(&context, "adapter")?),
            ("settings", native_field(&project, "settings")?),
            ("runtime", runtime),
            ("callbacks", hooks),
        ],
    )?;
    call_with(
        &registry::native(py, NativeAttr::WriteRuntimeTarget)?,
        &[
            (
                "target_dir",
                joined(&args.value("project_dir")?, &["target"])?,
            ),
            ("plan_output", plan),
            ("result", result.clone()),
        ],
    )?;
    let footer = call_with(
        &registry::native(py, NativeAttr::FormatBuildFooter)?,
        &[
            ("result", result.clone()),
            ("elapsed", native_field(&callbacks, "elapsed")?),
            ("use_color", color),
        ],
    )?;
    emit(&output, &format!("\n{}\n", footer.extract::<String>()?))?;
    Ok(i64::from(!native_field(&result, "status")?.eq(
        host::entry(py, ExecutorHost::BuildStatus)?.getattr("SUCCESS")?,
    )?))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(dbt_interop_plan_safety_gates, module)?)?;
    module.add_function(wrap_pyfunction!(execute_dbt_sqlbuild_work, module)?)
}
