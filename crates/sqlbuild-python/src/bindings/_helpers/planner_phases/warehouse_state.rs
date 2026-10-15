//! The warehouse inspection phase: snapshot, migrations and inspection relations in one pass.

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::planner_phases::constants::NATIVE_MODULE;
use crate::bindings::_helpers::planner_phases::full_refresh::effectively_full_refreshed_model_names;
use crate::bindings::_helpers::planner_phases::objects::{native, planner_model};
use crate::bindings::_helpers::planner_warehouse::fingerprint_cache::MigrationFingerprintCache;
use crate::bindings::_helpers::planner_warehouse::snapshot::{SnapshotRequest, warehouse_snapshot};
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult};
use pyo3::pyfunction;
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use std::time::Instant;

fn progress(runtime: &Bound<'_, PyAny>, message: &str) -> PyResult<()> {
    let on_progress = runtime.getattr("on_progress")?;
    if !on_progress.is_none() {
        on_progress.call1((message,))?;
    }
    Ok(())
}

#[pyfunction]
#[pyo3(signature = (*, runtime, scopes, overrides, deferral))]
pub(crate) fn gather_planner_warehouse_state<'py>(
    runtime: &Bound<'py, PyAny>,
    scopes: &Bound<'py, PyAny>,
    overrides: &Bound<'py, PyAny>,
    deferral: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = runtime.py();
    let started = Instant::now();
    let project = runtime.getattr("project")?;
    let fingerprints = Py::new(
        py,
        MigrationFingerprintCache::open(py, Some(project.getattr("compile_cache_dir")?))?,
    )?
    .into_bound(py)
    .into_any();
    progress(runtime, "Inspecting warehouse state...")?;
    let selected_scope = scopes.getattr("selected_scope")?;
    let full_refresh: bool = overrides.getattr("full_refresh")?.extract()?;
    let config = runtime.getattr("project_config")?;
    let cursor_scope = planner_model(
        py,
        "CursorSnapshotScope",
        &[
            ("model_keys", selected_scope.getattr("selected_keys")?),
            (
                "runtime_producer_keys",
                selected_scope.getattr("selected_keys")?,
            ),
            ("invocation_time", runtime.getattr("invocation_time")?),
            (
                "start_cursor_config",
                if config.is_none() {
                    py.None().into_bound(py)
                } else {
                    config.getattr("cursors")?.getattr("start")?
                },
            ),
            ("cursor_overrides", overrides.getattr("cursor_overrides")?),
        ],
    )?;
    let adapter = runtime.getattr("adapter")?;
    let stale_keys = pyo3::types::PyFrozenSet::new(
        py,
        scopes
            .getattr("stale_warning_scope")?
            .getattr("all_keys")?
            .call_method0("values")?
            .try_iter()?
            .collect::<PyResult<Vec<_>>>()?,
    )?
    .into_any();
    let snapshot = warehouse_snapshot(&SnapshotRequest {
        project: project.clone(),
        adapter: adapter.clone(),
        connection: runtime.getattr("connection")?,
        execute: adapter.getattr("execute")?,
        selected_keys: stale_keys,
        full_refresh: false,
        full_refresh_model_names: effectively_full_refreshed_model_names(&project, full_refresh)?,
        on_progress: runtime.getattr("on_progress")?,
        deferred_locations: deferral.getattr("deferred_locations")?,
        cursor_scope,
    })?;
    let migrations = native(
        py,
        "plan_model_migrations",
        &[
            ("runtime", runtime.clone()),
            ("scope", selected_scope.clone()),
            ("snapshot", snapshot.clone()),
            ("overrides", overrides.clone()),
            ("deferral", deferral.clone()),
            ("fingerprints", fingerprints.clone()),
        ],
    )?;
    fingerprints.call_method0("persist")?;
    let inspection_relations = call_with(
        &imported(py, NATIVE_MODULE, "build_planner_relations_context")?,
        &[
            ("project", project.clone()),
            ("adapter", adapter.clone()),
            ("connection", runtime.getattr("connection")?),
            ("scope", scopes.getattr("inspection_scope")?),
            ("deferral", deferral.clone()),
            ("project_config", config),
            ("local_config", runtime.getattr("local_config")?),
        ],
    )?;
    let physical = PyDict::new(py);
    for entry in migrations.getattr("entries")?.try_iter()? {
        let entry = entry?;
        if entry
            .getattr("decision")?
            .getattr("moves_data")?
            .is_truthy()?
        {
            let origin = entry.getattr("origin")?;
            let qualified = origin.getattr("qualified_name")?;
            physical.set_item(
                entry.getattr("model_name")?,
                if qualified.is_truthy()? {
                    qualified
                } else {
                    origin.getattr("name")?
                },
            )?;
        }
    }
    let columns = native(
        py,
        "plan_column_migrations",
        &[
            ("runtime", runtime.clone()),
            ("scope", selected_scope.clone()),
            ("snapshot", migrations.getattr("snapshot")?),
            (
                "full_refresh_model_names",
                effectively_full_refreshed_model_names(&project, full_refresh)?,
            ),
            ("physical_relations", physical.into_any()),
            ("overrides", overrides.clone()),
            ("deferral", deferral.clone()),
            (
                "source_columns",
                inspection_relations.getattr("source_warehouse_columns")?,
            ),
        ],
    )?;
    let old_names = native(
        py,
        "plan_old_name_views",
        &[
            ("runtime", runtime.clone()),
            ("scope", selected_scope),
            ("snapshot", snapshot),
            ("migration_entries", migrations.getattr("entries")?),
            ("column_entries", columns.getattr("entries")?),
        ],
    )?;
    if !runtime.getattr("on_progress")?.is_none() {
        progress(
            runtime,
            &format!(
                "Inspected warehouse state. ({:.2}s)",
                started.elapsed().as_secs_f64()
            ),
        )?;
        progress(runtime, "Generating plan...")?;
    }
    let mut warnings: Vec<_> = Vec::new();
    for source in [&migrations, &columns, &old_names] {
        for warning in source.getattr("warnings")?.try_iter()? {
            warnings.push(warning?);
        }
    }
    planner_model(
        py,
        "PlannerWarehouseState",
        &[
            ("snapshot", columns.getattr("snapshot")?),
            ("inspection_relations", inspection_relations),
            ("migration_entries", migrations.getattr("entries")?),
            ("migration_warnings", PyTuple::new(py, warnings)?.into_any()),
            ("column_migration_entries", columns.getattr("entries")?),
            ("column_rename_hints", columns.getattr("hints")?),
            ("old_name_view_entries", old_names.getattr("entries")?),
            ("old_name_views", old_names.getattr("views")?),
            ("migration_fingerprints", fingerprints),
        ],
    )
}
