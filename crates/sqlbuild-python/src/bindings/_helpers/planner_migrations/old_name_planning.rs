//! Old-name planning orchestration over existing live state inspection.

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::planner_migrations::column_objects::{model, native};
use crate::bindings::_helpers::planner_migrations::old_name_objects::recorded_view;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PySet, PySetMethods, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

fn schemas<'py>(
    args: &KeywordArguments<'py>,
    selected: &[Bound<'py, PyAny>],
) -> PyResult<Bound<'py, PyAny>> {
    let runtime = args.value("runtime")?;
    let py = runtime.py();
    let snapshot = args.value("snapshot")?;
    let needed = PySet::empty(py)?;
    for item in selected {
        let schema = item.getattr("destination")?.getattr("schema")?;
        if !schema.is_none() {
            needed.add(schema)?;
        }
    }
    for entry in args.value("migration_entries")?.try_iter()? {
        let schema = entry?.getattr("origin")?.getattr("schema")?;
        if !schema.is_none() {
            needed.add(schema)?;
        }
    }
    let mut include_project = runtime
        .getattr("project")?
        .getattr("unmatched_literal_sql_relations")?
        .is_truthy()?;
    if !include_project {
        for item in selected {
            let existing = snapshot
                .getattr("existing_relations")?
                .call_method1("get", (item.getattr("name")?,))?;
            if !existing.is_none()
                && imported(
                    py,
                    "sqlbuild.adapter.type_system.main.normalize_relation_type",
                    "normalize_relation_type",
                )?
                .call1((existing.getattr("relation_type")?,))?
                .eq("view")?
            {
                include_project = true;
                break;
            }
        }
    }
    if include_project {
        let project = native(py, "migration_project_schemas", &[("runtime", runtime)])?;
        for schema in project.try_iter()? {
            needed.add(schema?)?;
        }
    }
    native(
        py,
        "old_name_schemas_to_read",
        &[("snapshot", snapshot), ("needed", needed.into_any())],
    )
}

#[pyfunction]
#[pyo3(signature = (**options))]
fn plan_old_name_views<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "plan_old_name_views",
        options,
        (
            &[
                "runtime",
                "scope",
                "snapshot",
                "migration_entries",
                "column_entries",
            ],
            &[],
        ),
    )?;
    let runtime = args.value("runtime")?;
    let scope = args.value("scope")?;
    let project = runtime.getattr("project")?;
    let models: Vec<Bound<'py, PyAny>> = project
        .getattr("models")?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    let by_name = PyDict::new(py);
    for item in &models {
        by_name.set_item(item.getattr("name")?, item)?;
    }
    let mut selected: Vec<Bound<'py, PyAny>> = Vec::new();
    for key in scope.getattr("execution_order")?.try_iter()? {
        let key = key?;
        if scope.getattr("selected_keys")?.contains(&key)?
            && key.getattr("resource_type")?.eq("model")?
            && let Some(item) = by_name.get_item(key.getattr("name")?)?
        {
            selected.push(item);
        }
    }
    let state = call_with(
        &imported(
            py,
            "sqlbuild.compiler.planner.classes.migration_state_inspection",
            "MigrationStateInspection",
        )?,
        &[
            ("adapter", runtime.getattr("adapter")?),
            ("connection", runtime.getattr("connection")?),
            (
                "database",
                native(
                    py,
                    "migration_planning_database",
                    &[("runtime", runtime.clone())],
                )?,
            ),
        ],
    )?;
    let needed = schemas(&args, &selected)?;
    if needed.is_truthy()? {
        call_with(
            &state.getattr("inspect_old_name_views")?,
            &[("schemas", needed)],
        )?;
    }
    let target = project.getattr("effective_target_name")?;
    let mut histories: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut views: Vec<Bound<'py, PyAny>> = Vec::new();
    for history in state.getattr("old_name_histories")?.try_iter()? {
        let history = history?;
        let history_target = history.getattr("move")?.getattr("target_name")?;
        if !history_target.is_none() && !history_target.eq(&target)? {
            continue;
        }
        if !history.getattr("created")?.is_none() && history.getattr("dropped")?.is_none() {
            views.push(recorded_view(&runtime, &history, &models)?);
        }
        histories.push(history);
    }
    let views = PyTuple::new(py, views)?.into_any();
    let planner = super::models::OldNamePlanner::new(&args, models, histories, views.clone())?;
    let mut entries: Vec<Bound<'py, PyAny>> = Vec::new();
    let covered = PySet::empty(py)?;
    for entry in args.value("migration_entries")?.try_iter()? {
        let entry = entry?;
        let name = entry.getattr("model_name")?;
        if let Some(item) = by_name.get_item(&name)?
            && let Some(planned) = planner.for_migration(&entry, &item)?
        {
            entries.push(planned);
            covered.add(name)?;
        }
    }
    for item in &selected {
        if !covered.contains(item.getattr("name")?)?
            && let Some(planned) = planner.pending_for(item)?
        {
            entries.push(planned);
        }
    }
    let entries = PyTuple::new(py, entries)?.into_any();
    let claims = native(
        py,
        "old_name_claim_errors",
        &[
            ("selected", PyTuple::new(py, selected)?.into_any()),
            ("snapshot", args.value("snapshot")?),
            ("views", views.clone()),
            ("now", runtime.getattr("invocation_time")?),
        ],
    )?;
    let mut warnings: Vec<Bound<'py, PyAny>> = claims.try_iter()?.collect::<PyResult<_>>()?;
    warnings.extend(super::old_name_references::errors(
        &runtime, &views, &entries,
    )?);
    model(
        py,
        "OldNameViewPlanning",
        &[
            ("entries", entries),
            ("views", views),
            ("warnings", PyTuple::new(py, warnings)?.into_any()),
        ],
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(plan_old_name_views, module)?)
}
