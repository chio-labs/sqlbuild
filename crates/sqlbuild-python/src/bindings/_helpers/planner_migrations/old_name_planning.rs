//! Old-name planning orchestration over existing live state inspection.

use sqlbuild_host::entries::models::AdapterHost;

use crate::bindings::_helpers::boundary::python_calls::call_with;
use crate::bindings::_helpers::boundary::python_calls::keywords;
use crate::bindings::_helpers::compiled_views::model_reads;
use crate::bindings::_helpers::compiled_views::project_reads;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::planner_migrations::models::{MigrationPhase, OldNameViewPlanning};
use crate::bindings::_helpers::planner_migrations::old_name_objects::recorded_view;
use crate::bindings::_helpers::planner_migrations::old_names::old_name_claim_errors;
use crate::bindings::_helpers::planner_migrations::old_names::old_name_schemas_to_read;
use crate::bindings::_helpers::planner_phases::objects::object;
use crate::bindings::_helpers::planner_phases::runtime::runtime_field;
use crate::bindings::_helpers::records::fields::field as native_field;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PySet, PySetMethods, PyTuple};

fn schemas<'py>(
    (phase, migration_entries): (&MigrationPhase<'py>, &Bound<'py, PyAny>),
    selected: &[Bound<'py, PyAny>],
) -> PyResult<Bound<'py, PyAny>> {
    let runtime = phase.runtime.clone();
    let py = runtime.py();
    let snapshot = phase.snapshot.clone();
    let needed = PySet::empty(py)?;
    for item in selected {
        let schema = native_field(&model_reads::destination(item)?, "schema")?;
        if !schema.is_none() {
            needed.add(schema)?;
        }
    }
    for entry in migration_entries.try_iter()? {
        let schema = native_field(&native_field(&entry?, "origin")?, "schema")?;
        if !schema.is_none() {
            needed.add(schema)?;
        }
    }
    let mut include_project = native_field(
        &native_field(&runtime, "project")?,
        "unmatched_literal_sql_relations",
    )?
    .is_truthy()?;
    if !include_project {
        for item in selected {
            let existing = native_field(&snapshot, "existing_relations")?
                .call_method1("get", (model_reads::name_object(item)?,))?;
            if !existing.is_none()
                && host::entry(py, AdapterHost::NormalizeRelationType)?
                    .call1((native_field(&existing, "relation_type")?,))?
                    .eq("view")?
            {
                include_project = true;
                break;
            }
        }
    }
    if include_project {
        let project = super::planning_origin::project_schemas(&runtime)?;
        for schema in project.try_iter()? {
            needed.add(schema?)?;
        }
    }
    object(
        py,
        old_name_schemas_to_read(py, &snapshot, &needed.into_any())?,
    )
}

/// Old-name compatibility views to create, resume or retire for the planned model and column migrations.
pub(crate) fn plan_old_name_views<'py>(
    phase: &MigrationPhase<'py>,
    moves: (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<OldNameViewPlanning<'py>> {
    let py = phase.runtime.py();
    let runtime = phase.runtime.clone();
    let scope = phase.scope.clone();
    let project = runtime_field(&runtime, |runtime| &runtime.project)?;
    let models: Vec<Bound<'py, PyAny>> = project_reads::models(&project)?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    let by_name = PyDict::new(py);
    for item in &models {
        by_name.set_item(model_reads::name_object(item)?, item)?;
    }
    let mut selected: Vec<Bound<'py, PyAny>> = Vec::new();
    for key in native_field(&scope, "execution_order")?.try_iter()? {
        let key = key?;
        if native_field(&scope, "selected_keys")?.contains(&key)?
            && native_field(&key, "resource_type")?.eq("model")?
            && let Some(item) = by_name.get_item(native_field(&key, "name")?)?
        {
            selected.push(item);
        }
    }
    let state = super::state_inspection::inspection(&runtime, None)?;
    let needed = schemas((phase, moves.0), &selected)?;
    if needed.is_truthy()? {
        call_with(
            &native_field(&state, "inspect_old_name_views")?,
            &[("schemas", needed)],
        )?;
    }
    let target = native_field(&project, "effective_target_name")?;
    let mut histories: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut views: Vec<Bound<'py, PyAny>> = Vec::new();
    for history in native_field(&state, "old_name_histories")?.try_iter()? {
        let history = history?;
        let history_target = native_field(&native_field(&history, "move")?, "target_name")?;
        if !history_target.is_none() && !history_target.eq(&target)? {
            continue;
        }
        if !native_field(&history, "created")?.is_none()
            && native_field(&history, "dropped")?.is_none()
        {
            views.push(recorded_view(&runtime, &history, &models)?);
        }
        histories.push(history);
    }
    let views = PyTuple::new(py, views)?.into_any();
    let planner = super::models::OldNamePlanner::new(
        (&phase.runtime, moves.1),
        models,
        histories,
        views.clone(),
    )?;
    let mut entries: Vec<Bound<'py, PyAny>> = Vec::new();
    let covered = PySet::empty(py)?;
    for entry in moves.0.try_iter()? {
        let entry = entry?;
        let name = native_field(&entry, "model_name")?;
        if let Some(item) = by_name.get_item(&name)?
            && let Some(planned) = planner.for_migration(&entry, &item)?
        {
            entries.push(planned);
            covered.add(name)?;
        }
    }
    for item in &selected {
        if !covered.contains(model_reads::name_object(item)?)?
            && let Some(planned) = planner.pending_for(item)?
        {
            entries.push(planned);
        }
    }
    let entries = PyTuple::new(py, entries)?.into_any();
    let claims = object(
        py,
        old_name_claim_errors(
            py,
            Some(keywords(
                py,
                &[
                    ("selected", PyTuple::new(py, selected)?.into_any()),
                    ("snapshot", phase.snapshot.clone()),
                    ("views", views.clone()),
                    (
                        "now",
                        runtime_field(&runtime, |runtime| &runtime.invocation_time)?,
                    ),
                ],
            )?),
        )?,
    )?;
    let mut warnings: Vec<Bound<'py, PyAny>> = claims.try_iter()?.collect::<PyResult<_>>()?;
    warnings.extend(super::old_name_references::errors(
        &runtime, &views, &entries,
    )?);
    Ok(OldNameViewPlanning {
        entries,
        views,
        warnings,
    })
}
