//! Assemble migration policy and redirected live cursor inspection requests.

use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, call_with};
use crate::bindings::_helpers::planner_migrations::column_objects::native;
use crate::bindings::_helpers::planner_phases::runtime::runtime_field;
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::PyDict;
use pyo3::{pyfunction, wrap_pyfunction};

#[pyfunction]
#[pyo3(signature = (*, runtime))]
fn migration_missing_origin_policy<'py>(
    runtime: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    call_with(
        &registry::native(runtime.py(), NativeAttr::EffectiveTargetConfig)?,
        &[("runtime", runtime.clone())],
    )?
    .getattr("missing_migration_origin")
}

#[pyfunction]
#[pyo3(signature = (**options))]
fn migration_redirected_cursor_snapshots<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "migration_redirected_cursor_snapshots",
        options,
        (
            &[
                "runtime",
                "scope",
                "existing_relations",
                "target_relations",
                "overrides",
                "deferral",
            ],
            &["origin_cursor_columns"],
        ),
    )?;
    let runtime = args.value("runtime")?;
    let scope = args.value("scope")?;
    let overrides = args.value("overrides")?;
    let project = runtime_field(&runtime, |runtime| &runtime.project)?;
    let config = runtime_field(&runtime, |runtime| &runtime.project_config)?;
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
                runtime_field(&runtime, |runtime| &runtime.invocation_time)?,
            ),
            ("start_cursor_config", start),
            ("cursor_overrides", overrides.getattr("cursor_overrides")?),
        ],
    )?;
    let full_refresh = call_with(
        &registry::native(py, NativeAttr::EffectivelyFullRefreshedModelNames)?,
        &[
            ("project", project.clone()),
            ("cli_full_refresh", overrides.getattr("full_refresh")?),
        ],
    )?;
    call_with(
        &registry::native(py, NativeAttr::GatherRedirectedCursorSnapshots)?,
        &[
            ("project", project),
            (
                "adapter",
                runtime_field(&runtime, |runtime| &runtime.adapter)?,
            ),
            (
                "connection",
                runtime_field(&runtime, |runtime| &runtime.connection)?,
            ),
            ("existing_relations", args.value("existing_relations")?),
            ("target_relations", args.value("target_relations")?),
            ("cursor_scope", cursor_scope),
            ("full_refresh_model_names", full_refresh),
            (
                "deferred_locations",
                args.value("deferral")?.getattr("deferred_locations")?,
            ),
            (
                "on_progress",
                runtime_field(&runtime, |runtime| &runtime.on_progress)?,
            ),
            (
                "origin_cursor_columns",
                args.value("origin_cursor_columns")?,
            ),
        ],
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(migration_missing_origin_policy, module)?)?;
    module.add_function(wrap_pyfunction!(
        migration_redirected_cursor_snapshots,
        module
    )?)
}
