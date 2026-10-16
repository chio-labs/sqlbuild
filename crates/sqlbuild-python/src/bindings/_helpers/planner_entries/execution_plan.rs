//! Top-level planner orchestration producing an execution plan.

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported, within,
};
use crate::bindings::_helpers::native_host::adapter::AdapterHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::planner_entries::test_planning::{
    PlanningRequest, SqlTestPlanning, start_planning,
};
use crate::bindings::_helpers::planner_entries::values::{COMPILE_TYPES, native, replaced};
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use std::time::Instant;

const INSPECTION_CATALOG: AdapterHost = AdapterHost::OpenInspectionCatalog;
/// Selected scopes, and the overrides with cursor overrides typed for the selected models.
fn scopes_and_cursor_overrides<'py>(
    args: &KeywordArguments<'py>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let project = args.value("project")?;
    let py = project.py();
    let scopes = native(
        py,
        NativeAttr::ResolvePlannerScopes,
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
        NativeAttr::TypeCursorOverrides,
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
        NativeAttr::DetectChanges,
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
        let empty = native(
            py,
            RecordId::PlannerChangeResults,
            &[
                ("models", PyDict::new(py).into_any()),
                ("functions", PyDict::new(py).into_any()),
            ],
        )?;
        return Ok((changes, empty));
    }
    let stale = native(
        py,
        NativeAttr::DetectStaleWarningChanges,
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
    test_planning: &SqlTestPlanning,
) -> PyResult<Bound<'py, PyAny>> {
    let project = args.value("project")?;
    let py = project.py();
    let deferral = args.value("deferral")?;
    let policies = args.value("policies")?;
    let warehouse = native(
        py,
        NativeAttr::GatherPlannerWarehouseState,
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
        NativeAttr::BuildPlannerIdentityContext,
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
        NativeAttr::CheckSelectedScopeBuildability,
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
        NativeAttr::ResolveModelActions,
        &[
            ("scope", inspection_scope.clone()),
            ("changes", changes.clone()),
        ],
    )?;
    let source_freshness = native(
        py,
        NativeAttr::BuildPlannerSourceFreshnessResult,
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
        NativeAttr::PrunePlannerExecutionScope,
        &[
            ("scopes", scopes.clone()),
            ("resolved_actions", resolved_actions),
        ],
    )?;
    let reconciliation = native(
        py,
        NativeAttr::ReconcileExecutionChanges,
        &[
            ("warehouse", warehouse.clone()),
            ("identities", identities.clone()),
            ("pruning", pruning.clone()),
            ("changes", changes),
        ],
    )?;
    let entries = native(
        py,
        NativeAttr::BuildPlannerEntryResults,
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
    let planned_sql_tests = test_planning.result(py)?.into_bound(py);
    let mut plan_output = native(
        py,
        NativeAttr::AssembleBasePlanOutput,
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
        NativeAttr::WithStoragePolicies,
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
        NativeAttr::WithPlanWarnings,
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
        NativeAttr::WithPlanMetadata,
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
    let runtime = native(
        py,
        RecordId::PlannerRuntime,
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
    let test_planning = start_planning(
        py,
        PlanningRequest {
            project: project.clone().unbind(),
            adapter: adapter.clone().unbind(),
            selected_keys: inspection.getattr("selected_keys")?.unbind(),
            sql_test_selection: inspection.getattr("sql_test_selection")?.unbind(),
        },
        args.value("policies")?
            .getattr("plan_sql_tests")?
            .is_truthy()?,
    )?;
    let planned = (|| {
        let catalog = call_with(
            &host::entry(py, INSPECTION_CATALOG)?,
            &[("adapter", adapter), ("connection", connection)],
        )?;
        within(&catalog, |_| {
            planned_output(&args, &runtime, (&scopes, &overrides), test_planning.get())
        })
    })();
    let joined = test_planning.get().result(py);
    let planned = planned?;
    joined?;
    Ok(planned)
}

/// Add the execution plan entry point.
pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_execution_plan, module)?)
}
