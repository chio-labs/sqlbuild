//! `sqb janitor` phases: compile, connect, inspect and plan, clean up and close.

use std::time::Instant;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods};

use crate::bindings::_helpers::build_progress::transient_status::status_reporter;
use crate::bindings::_helpers::command_runtime::invocation::resolve_adapter_connection_context;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, within};
use crate::bindings::_helpers::janitor::janitor_facts::Warehouse;
use crate::bindings::_helpers::janitor::janitor_planning::{
    JanitorSettings, RelationScope, build_plan,
};

const NATIVE_MODULE: &str = "sqlbuild._native";
const LIFECYCLE_MODULE: &str = "sqlbuild.runtime.observability.classes.operation_lifecycle";
const JANITOR_EXECUTE_MODULE: &str = "sqlbuild.executor.janitor.main.execute";
const ERRORS_MODULE: &str = "sqlbuild._native";
const UNKNOWN_VIEW_CODE: &str = "C503";
const UNKNOWN_VIEW_HELP: &str =
    "Run sqb janitor without --drop-old-name-view to list compatibility views.";
const CANDIDATE_FIELDS: [&str; 4] = [
    "candidates",
    "archive_deletion_candidates",
    "query_diff_artifact_candidates",
    "direct_state_prune_candidates",
];

/// The compiled project, its adapter and the active target connection settings.
pub(crate) struct JanitorCompiled<'py> {
    pub(crate) adapter_name: Bound<'py, PyAny>,
    pub(crate) adapter: Bound<'py, PyAny>,
    pub(crate) project: Bound<'py, PyAny>,
    pub(crate) connection_config: Bound<'py, PyAny>,
}

fn stdout(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    py.import("sys")?.getattr("stdout")
}

fn use_color(invocation: &Bound<'_, PyAny>) -> PyResult<bool> {
    invocation.getattr("use_color")?.extract()
}

/// `OperationLifecycle(operation_kind=..., operation_name=...)`.
fn lifecycle<'py>(py: Python<'py>, (kind, name): (&str, &str)) -> PyResult<Bound<'py, PyAny>> {
    let options: Bound<'py, PyDict> = PyDict::new(py);
    options.set_item("operation_kind", kind)?;
    options.set_item("operation_name", name)?;
    imported(py, LIFECYCLE_MODULE, "OperationLifecycle")?.call((), Some(&options))
}

/// Compile for the janitor or `--as` target and resolve the active target connection.
pub(crate) fn compile_janitor_project<'py>(
    invocation: &Bound<'py, PyAny>,
) -> PyResult<JanitorCompiled<'py>> {
    let py: Python<'py> = invocation.py();
    let context: Bound<'py, PyAny> = resolve_adapter_connection_context(
        &invocation.getattr("discovered_inputs")?,
        &invocation.getattr("effective_project_dir")?,
        (
            invocation.getattr("selected_target")?,
            py.None().into_bound(py),
        ),
        true,
    )?;
    let started: Instant = Instant::now();
    let status: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "PlanningProgressReporter")?,
        &[
            ("stream", stdout(py)?),
            (
                "use_color",
                PyBool::new(py, use_color(invocation)?)
                    .to_owned()
                    .into_any(),
            ),
        ],
    )?;
    let as_target: Bound<'py, PyAny> = invocation.getattr("as_target")?;
    let target: Bound<'py, PyAny> = if as_target.is_none() {
        invocation.getattr("selected_target")?
    } else {
        as_target
    };
    let project: Bound<'py, PyAny> =
        within(&lifecycle(py, ("project", "project_compile"))?, |_| {
            status.call_method1("on_progress", ("Compiling project...",))?;
            let project: Bound<'py, PyAny> = call_with(
                &imported(py, NATIVE_MODULE, "build_compiled_project")?,
                &[
                    (
                        "discovered_inputs",
                        invocation.getattr("discovered_inputs")?,
                    ),
                    ("adapter", context.getattr("adapter")?),
                    ("selected_target", target),
                    ("resolved_connection", context.getattr("connection_config")?),
                ],
            )?;
            status.call_method1(
                "on_progress",
                (format!(
                    "Compiled project. ({:.2}s)",
                    started.elapsed().as_secs_f64()
                ),),
            )?;
            Ok(project)
        })?;
    Ok(JanitorCompiled {
        adapter_name: context.getattr("adapter_name")?,
        adapter: context.getattr("adapter")?,
        project,
        connection_config: context.getattr("connection_config")?,
    })
}

fn connection_timing(progress: &Bound<'_, PyAny>, method: &str, started: Instant) -> PyResult<()> {
    let options: Bound<'_, PyDict> = PyDict::new(progress.py());
    options.set_item("connection_count", 1)?;
    options.set_item("elapsed_seconds", started.elapsed().as_secs_f64())?;
    progress.call_method(method, (), Some(&options))?;
    Ok(())
}

/// Connect to the janitor target warehouse.
pub(crate) fn connect_janitor_warehouse<'py>(
    invocation: &Bound<'py, PyAny>,
    compiled: &JanitorCompiled<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = invocation.py();
    let progress: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "ConnectionProgressReporter")?,
        &[
            ("adapter_name", compiled.adapter_name.clone()),
            ("stream", stdout(py)?),
            (
                "use_color",
                PyBool::new(py, use_color(invocation)?)
                    .to_owned()
                    .into_any(),
            ),
        ],
    )?;
    let started: Instant = Instant::now();
    progress.call_method1("on_connection_start", (1,))?;
    let connected: PyResult<Bound<'py, PyAny>> = within(
        &lifecycle(py, ("janitor", "janitor_target_connection"))?,
        |_| {
            compiled
                .adapter
                .call_method1("connect", (&compiled.connection_config,))
        },
    );
    match connected {
        Ok(connection) => {
            connection_timing(&progress, "on_connection_complete", started)?;
            Ok(connection)
        }
        Err(error) => {
            connection_timing(&progress, "on_connection_error", started)?;
            Err(error)
        }
    }
}

/// Close the janitor warehouse connection.
pub(crate) fn close_janitor_warehouse(
    compiled: &JanitorCompiled<'_>,
    connection: &Bound<'_, PyAny>,
) -> PyResult<()> {
    compiled.adapter.call_method1("close", (connection,))?;
    Ok(())
}

fn candidate_count(plan: &Bound<'_, PyAny>) -> PyResult<usize> {
    let mut count: usize = plan.getattr("old_name_views")?.getattr("drops")?.len()?;
    for field in CANDIDATE_FIELDS {
        count += plan.getattr(field)?.len()?;
    }
    Ok(count)
}

fn unknown_view_error(py: Python<'_>, requests: &Bound<'_, PyAny>) -> PyResult<PyErr> {
    let names: Vec<String> = requests.extract()?;
    let options: Bound<'_, PyDict> = PyDict::new(py);
    options.set_item("code", UNKNOWN_VIEW_CODE)?;
    options.set_item("help", UNKNOWN_VIEW_HELP)?;
    let error: Bound<'_, PyAny> = imported(py, ERRORS_MODULE, "CliUserError")?.call(
        (format!(
            "no compatibility view is recorded at {}",
            names.join(", ")
        ),),
        Some(&options),
    )?;
    Ok(PyErr::from_value(error))
}

/// Build the janitor execution plan from warehouse facts.
pub(crate) fn build_janitor_execution_plan<'py>(
    (invocation, settings): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    compiled: &JanitorCompiled<'py>,
    connection: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = invocation.py();
    let started: Instant = Instant::now();
    let status: Bound<'py, PyAny> = status_reporter(&stdout(py)?, use_color(invocation)?)?;
    status.call_method1("start", ("Inspecting warehouse state...",))?;
    let janitor: Bound<'py, PyAny> = invocation
        .getattr("discovered_inputs")?
        .getattr("project_config")?
        .getattr("janitor")?;
    let plan: Bound<'py, PyAny> = within(
        &lifecycle(py, ("janitor", "janitor_candidate_planning"))?,
        |lifecycle| {
            let plan: Bound<'py, PyAny> = build_plan(
                (
                    &compiled.project,
                    &Warehouse {
                        adapter: compiled.adapter.clone(),
                        connection: connection.clone(),
                    },
                ),
                &JanitorSettings {
                    retention_days: settings.getattr("retention_days")?.extract()?,
                    delete_tracked_only: janitor.getattr("delete_tracked_only")?.is_truthy()?,
                    exclude_patterns: janitor.getattr("exclude_patterns")?.extract()?,
                    direct_mode: true,
                    state_history_versions: settings
                        .getattr("direct_state_history_versions")?
                        .extract()?,
                    archive_retention_days: settings
                        .getattr("archive_retention_days")?
                        .extract()?,
                    early_old_name_view_drops: settings
                        .getattr("drop_old_name_views")?
                        .extract()?,
                },
                &RelationScope {
                    scan_keys: Vec::new(),
                    protected_keys: Vec::new(),
                    reasons: Vec::new(),
                },
            )?;
            let metadata: Bound<'py, PyDict> = PyDict::new(py);
            metadata.set_item("item_count", candidate_count(&plan)?)?;
            let options: Bound<'py, PyDict> = PyDict::new(py);
            options.set_item("metadata", metadata)?;
            lifecycle.call_method("completed", (), Some(&options))?;
            Ok(plan)
        },
    )?;
    let options: Bound<'py, PyDict> = PyDict::new(py);
    options.set_item(
        "message",
        format!(
            "Inspected warehouse state. ({:.2}s)",
            started.elapsed().as_secs_f64()
        ),
    )?;
    options.set_item("blank_line_after", true)?;
    status.call_method("complete", (), Some(&options))?;
    let unknown: Bound<'py, PyAny> = plan
        .getattr("old_name_views")?
        .getattr("unknown_requests")?;
    if unknown.is_truthy()? {
        return Err(unknown_view_error(py, &unknown)?);
    }
    Ok(plan)
}

/// Execute the warehouse cleanup plan.
pub(crate) fn execute_janitor_cleanup<'py>(
    compiled: &JanitorCompiled<'py>,
    connection: &Bound<'py, PyAny>,
    plan: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    call_with(
        &imported(
            compiled.adapter.py(),
            JANITOR_EXECUTE_MODULE,
            "execute_janitor_plan",
        )?,
        &[
            ("plan", plan.clone()),
            ("adapter", compiled.adapter.clone()),
            ("connection", connection.clone()),
        ],
    )
}
