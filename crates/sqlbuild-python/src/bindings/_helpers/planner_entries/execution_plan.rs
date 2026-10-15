//! Top-level planner orchestration producing an execution plan.

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported, within,
};
use crate::bindings::_helpers::planner_entries::values::{
    COMPILE_TYPES, boolean, native, planner_model, replaced, string,
};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use std::time::Instant;

const INSPECTION_CATALOG: (&str, &str) = (
    "sqlbuild.adapter.relations.main.open_inspection_catalog",
    "open_inspection_catalog",
);
const TEST_PLANNING_THREAD: &str = "sqlbuild-test-planning";

/// A future resolving to the planned SQL tests, planned on a daemon thread when enabled.
fn sql_test_planning<'py>(
    (project, adapter): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    (selected_keys, sql_test_selection): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    enabled: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let py = project.py();
    let future = imported(py, "concurrent.futures", "Future")?.call0()?;
    if !enabled {
        future.call_method1(
            "set_result",
            (planner_model(
                py,
                "PlannedSqlTests",
                &[
                    ("selected_keys", selected_keys.clone()),
                    ("sql_test_selection", sql_test_selection.clone()),
                ],
            )?,),
        )?;
        return Ok(future);
    }
    let kwargs = PyDict::new(py);
    kwargs.set_item("future", &future)?;
    kwargs.set_item("project", project)?;
    kwargs.set_item("adapter", adapter)?;
    kwargs.set_item("selected_keys", selected_keys)?;
    kwargs.set_item("sql_test_selection", sql_test_selection)?;
    call_with(
        &imported(py, "threading", "Thread")?,
        &[
            (
                "target",
                imported(py, "sqlbuild._native", "plan_selected_sql_tests_into")?,
            ),
            ("kwargs", kwargs.into_any()),
            ("name", string(py, TEST_PLANNING_THREAD)),
            ("daemon", boolean(py, true)?),
        ],
    )?
    .call_method0("start")?;
    Ok(future)
}

/// Selected scopes, and the overrides with cursor overrides typed for the selected models.
fn scopes_and_cursor_overrides<'py>(
    args: &KeywordArguments<'py>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let project = args.value("project")?;
    let py = project.py();
    let scopes = native(
        py,
        "resolve_planner_scopes",
        &[
            ("project", project.clone()),
            ("selection", args.value("selection")?),
            ("policies", args.value("policies")?),
        ],
    )?;
    let selected = scopes.getattr("selected_scope")?;
    let models_by_name = selected.getattr("models_by_name")?;
    let model_type = imported(py, COMPILE_TYPES, "CompiledResourceType")?.getattr("MODEL")?;
    let mut models: Vec<Bound<'py, PyAny>> = Vec::new();
    for key in selected.getattr("selected_keys")?.try_iter()? {
        let key = key?;
        let name = key.getattr("name")?;
        if key.getattr("resource_type")?.eq(&model_type)? && models_by_name.contains(&name)? {
            models.push(models_by_name.get_item(&name)?);
        }
    }
    let overrides = args.value("overrides")?;
    let typed = native(
        py,
        "type_cursor_overrides",
        &[
            ("cursor_overrides", overrides.getattr("cursor_overrides")?),
            ("selected_models", PyTuple::new(py, models)?.into_any()),
        ],
    )?;
    Ok((
        scopes,
        replaced(&overrides, &[("cursor_overrides", typed)])?,
    ))
}

/// Execution and stale-warning change results for the inspected scopes.
fn change_results<'py>(
    project: &Bound<'py, PyAny>,
    (scopes, snapshot, identities): (&Bound<'py, PyAny>, &Bound<'py, PyAny>, &Bound<'py, PyAny>),
    overrides: &Bound<'py, PyAny>,
    policies: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let py = project.py();
    let versions = identities.getattr("version_identities")?;
    let changes = native(
        py,
        "detect_changes",
        &[
            ("project", project.clone()),
            ("scope", scopes.getattr("inspection_scope")?),
            ("snapshot", snapshot.clone()),
            ("full_refresh", overrides.getattr("full_refresh")?),
            (
                "expected_version_hashes",
                versions.getattr("model_version_hashes")?,
            ),
            (
                "expected_metadata_jsons",
                versions.getattr("model_metadata_jsons")?,
            ),
        ],
    )?;
    if !policies.getattr("selection_diagnostics")?.is_truthy()? {
        let empty = planner_model(
            py,
            "PlannerChangeResults",
            &[
                ("models", PyDict::new(py).into_any()),
                ("functions", PyDict::new(py).into_any()),
            ],
        )?;
        return Ok((changes, empty));
    }
    let stale = native(
        py,
        "detect_stale_warning_changes",
        &[
            ("project", project.clone()),
            ("scopes", scopes.clone()),
            ("snapshot", snapshot.clone()),
            ("identities", identities.clone()),
            ("execution_changes", changes.clone()),
        ],
    )?;
    Ok((changes, stale))
}

/// The plan phases after warehouse inspection, run inside the inspection catalog.
fn planned_output<'py>(
    args: &KeywordArguments<'py>,
    runtime: &Bound<'py, PyAny>,
    (scopes, overrides): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    test_planning: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let project = args.value("project")?;
    let py = project.py();
    let deferral = args.value("deferral")?;
    let policies = args.value("policies")?;
    let warehouse = native(
        py,
        "gather_planner_warehouse_state",
        &[
            ("runtime", runtime.clone()),
            ("scopes", scopes.clone()),
            ("overrides", overrides.clone()),
            ("deferral", deferral.clone()),
        ],
    )?;
    let started = Instant::now();
    let identities = native(
        py,
        "build_planner_identity_context",
        &[
            ("project", project.clone()),
            ("scopes", scopes.clone()),
            (
                "include_stale_warning_identities",
                policies.getattr("selection_diagnostics")?,
            ),
        ],
    )?;
    native(
        py,
        "check_selected_scope_buildability",
        &[
            ("runtime", runtime.clone()),
            ("scopes", scopes.clone()),
            ("warehouse", warehouse.clone()),
            ("deferral", deferral.clone()),
        ],
    )?;
    let snapshot = warehouse.getattr("snapshot")?;
    let (changes, stale_warning_changes) = change_results(
        &project,
        (scopes, &snapshot, &identities),
        overrides,
        &policies,
    )?;
    let inspection_scope = scopes.getattr("inspection_scope")?;
    let resolved_actions = native(
        py,
        "resolve_model_actions",
        &[
            ("scope", inspection_scope.clone()),
            ("changes", changes.clone()),
        ],
    )?;
    let source_freshness = native(
        py,
        "build_planner_source_freshness_result",
        &[
            ("project", project.clone()),
            ("adapter", args.value("adapter")?),
            ("connection", args.value("connection")?),
            ("scope", inspection_scope),
            ("relations", warehouse.getattr("inspection_relations")?),
            (
                "freshness_state_schemas",
                snapshot.getattr("source_freshness_state_schemas")?,
            ),
        ],
    )?;
    let pruning = native(
        py,
        "prune_planner_execution_scope",
        &[
            ("scopes", scopes.clone()),
            ("resolved_actions", resolved_actions),
        ],
    )?;
    let reconciliation = native(
        py,
        "reconcile_execution_changes",
        &[
            ("warehouse", warehouse.clone()),
            ("identities", identities.clone()),
            ("pruning", pruning.clone()),
            ("changes", changes),
        ],
    )?;
    let entries = native(
        py,
        "build_planner_entry_results",
        &[
            ("runtime", runtime.clone()),
            ("warehouse", warehouse.clone()),
            ("identities", identities.clone()),
            ("overrides", overrides.clone()),
            ("policies", policies.clone()),
            ("deferral", deferral),
            ("pruning", pruning.clone()),
            ("reconciliation", reconciliation.clone()),
            ("source_freshness", source_freshness.clone()),
        ],
    )?;
    let planned_sql_tests = test_planning.call_method0("result")?;
    let mut plan_output = native(
        py,
        "assemble_base_plan_output",
        &[
            ("runtime", runtime.clone()),
            ("warehouse", warehouse.clone()),
            ("identities", identities.clone()),
            ("overrides", overrides.clone()),
            ("pruning", pruning.clone()),
            ("reconciliation", reconciliation),
            ("entries", entries),
            ("source_freshness", source_freshness.clone()),
            ("planned_sql_tests", planned_sql_tests),
        ],
    )?;
    plan_output = native(
        py,
        "with_storage_policies",
        &[
            ("plan_output", plan_output),
            ("runtime", runtime.clone()),
            ("warehouse", warehouse.clone()),
            ("scopes", scopes.clone()),
            ("policies", policies.clone()),
        ],
    )?;
    plan_output = native(
        py,
        "with_plan_warnings",
        &[
            ("runtime", runtime.clone()),
            ("scopes", scopes.clone()),
            ("warehouse", warehouse),
            ("identities", identities),
            ("stale_warning_changes", stale_warning_changes),
            ("pruning", pruning.clone()),
            ("source_freshness", source_freshness.clone()),
            ("plan_output", plan_output),
            ("policies", policies.clone()),
        ],
    )?;
    plan_output = native(
        py,
        "with_plan_metadata",
        &[
            ("plan_output", plan_output),
            ("pruning", pruning),
            ("source_freshness", source_freshness),
            ("policies", policies),
        ],
    )?;
    let on_progress = args.value("on_progress")?;
    if !on_progress.is_none() {
        on_progress.call1((format!(
            "Generated plan. ({:.2}s)",
            started.elapsed().as_secs_f64()
        ),))?;
    }
    Ok(plan_output)
}

/// Build the execution plan for one selection against live warehouse state.
#[pyfunction]
#[pyo3(signature = (**kwargs))]
fn build_execution_plan<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "build_execution_plan",
        kwargs,
        (
            &[
                "project",
                "adapter",
                "connection",
                "selection",
                "overrides",
                "deferral",
                "policies",
            ],
            &["on_progress", "project_config", "local_config"],
        ),
    )?;
    let project = args.value("project")?;
    let adapter = args.value("adapter")?;
    let connection = args.value("connection")?;
    let runtime = planner_model(
        py,
        "PlannerRuntime",
        &[
            ("project", project.clone()),
            ("adapter", adapter.clone()),
            ("connection", connection.clone()),
            ("project_config", args.value("project_config")?),
            ("local_config", args.value("local_config")?),
            ("on_progress", args.value("on_progress")?),
        ],
    )?;
    let (scopes, overrides) = scopes_and_cursor_overrides(&args)?;
    let inspection = scopes.getattr("inspection_scope")?;
    let test_planning = sql_test_planning(
        (&project, &adapter),
        (
            &inspection.getattr("selected_keys")?,
            &inspection.getattr("sql_test_selection")?,
        ),
        args.value("policies")?
            .getattr("plan_sql_tests")?
            .is_truthy()?,
    )?;
    let catalog = call_with(
        &imported(py, INSPECTION_CATALOG.0, INSPECTION_CATALOG.1)?,
        &[("adapter", adapter), ("connection", connection)],
    )?;
    within(&catalog, |_| {
        planned_output(&args, &runtime, (&scopes, &overrides), &test_planning)
    })
}

/// Start SQL test planning on a daemon thread, or resolve to no tests when disabled.
#[pyfunction]
#[pyo3(signature = (**kwargs))]
fn start_sql_test_planning<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "start_sql_test_planning",
        kwargs,
        (
            &[
                "project",
                "adapter",
                "selected_keys",
                "sql_test_selection",
                "enabled",
            ],
            &[],
        ),
    )?;
    sql_test_planning(
        (&args.value("project")?, &args.value("adapter")?),
        (
            &args.value("selected_keys")?,
            &args.value("sql_test_selection")?,
        ),
        args.flag("enabled")?,
    )
}

pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_execution_plan, module)?)?;
    module.add_function(wrap_pyfunction!(start_sql_test_planning, module)?)
}
