//! Assemble migration policy and redirected live cursor inspection requests.

use crate::bindings::_helpers::compile_driver::python_calls::call_with;
use crate::bindings::_helpers::planner_migrations::column_objects::native;
use crate::bindings::_helpers::planner_migrations::models::MigrationPhase;
use crate::bindings::_helpers::planner_phases::full_refresh::effectively_full_refreshed_model_names;
use crate::bindings::_helpers::planner_phases::retention::effective_target_config;
use crate::bindings::_helpers::planner_phases::runtime::runtime_field;
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};

/// The target's policy for migration origins that no longer exist.
pub(super) fn missing_origin_policy<'py>(
    runtime: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    effective_target_config(runtime)?.getattr("missing_migration_origin")
}

/// Live cursor snapshots of models whose history now sits in a redirected relation.
pub(super) fn redirected_cursor_snapshots<'py>(
    phase: &MigrationPhase<'py>,
    (existing_relations, target_relations): (Bound<'py, PyAny>, Bound<'py, PyAny>),
    origin_cursor_columns: Option<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    let runtime = &phase.runtime;
    let py = runtime.py();
    let overrides = &phase.overrides;
    let scope = &phase.scope;
    let project = runtime_field(runtime, |runtime| &runtime.project)?;
    let config = runtime_field(runtime, |runtime| &runtime.project_config)?;
    let start = if config.is_none() {
        py.None().into_bound(py)
    } else {
        config.getattr("cursors")?.getattr("start")?
    };
    let cursor_scope = native(
        py,
        RecordId::CursorSnapshotScope,
        &[
            ("model_keys", scope.getattr("selected_keys")?),
            ("runtime_producer_keys", scope.getattr("selected_keys")?),
            (
                "invocation_time",
                runtime_field(runtime, |runtime| &runtime.invocation_time)?,
            ),
            ("start_cursor_config", start),
            ("cursor_overrides", overrides.getattr("cursor_overrides")?),
        ],
    )?;
    let full_refresh = effectively_full_refreshed_model_names(
        &project,
        overrides.getattr("full_refresh")?.is_truthy()?,
    )?;
    call_with(
        &registry::native(py, NativeAttr::GatherRedirectedCursorSnapshots)?,
        &[
            ("project", project),
            (
                "adapter",
                runtime_field(runtime, |runtime| &runtime.adapter)?,
            ),
            (
                "connection",
                runtime_field(runtime, |runtime| &runtime.connection)?,
            ),
            ("existing_relations", existing_relations),
            ("target_relations", target_relations),
            ("cursor_scope", cursor_scope),
            ("full_refresh_model_names", full_refresh),
            (
                "deferred_locations",
                phase.deferral.getattr("deferred_locations")?,
            ),
            (
                "on_progress",
                runtime_field(runtime, |runtime| &runtime.on_progress)?,
            ),
            (
                "origin_cursor_columns",
                origin_cursor_columns.unwrap_or_else(|| py.None().into_bound(py)),
            ),
        ],
    )
}
