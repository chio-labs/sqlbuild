//! Old-name planner object conversions and existing native helper calls.

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::planner_migrations::column_objects::{config, model};
use crate::bindings::_helpers::state_rows::migration_projections::old_name_retention;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};

pub(super) fn relation<'py>(location: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    imported(
        location.py(),
        "sqlbuild.executor.migrations._helpers.relation_for_location",
        "migration_relation_for_location",
    )?
    .call1((location,))
}

pub(super) fn location<'py>(
    runtime: &Bound<'py, PyAny>,
    relation: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let mut fields = vec![
        ("database", relation.getattr("database")?),
        ("schema", relation.getattr("schema")?),
        ("name", relation.getattr("name")?),
    ];
    let qualified = call_with(
        &runtime
            .getattr("adapter")?
            .getattr("render_qualified_name")?,
        &fields,
    )?;
    fields.push(("qualified_name", qualified));
    call_with(
        &imported(
            runtime.py(),
            "sqlbuild.compiler.compile.models",
            "CompiledRelationLocation",
        )?,
        &fields,
    )
}

pub(super) fn stores_history(item: &Bound<'_, PyAny>) -> PyResult<bool> {
    let materialization = config(item, "materialized")?;
    Ok(materialization.eq("incremental")? || materialization.eq("snapshot")?)
}

pub(super) fn retention<'py>(
    item: &Bound<'py, PyAny>,
    project: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    old_name_retention(&item.getattr("config")?.getattr("values")?, project)
}

pub(super) fn expires<'py>(
    retention: &Bound<'py, PyAny>,
    now: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let duration = imported(now.py(), "sqlbuild.cursor_algebra.models", "Duration")?
        .call_method1("parse", (retention,))?;
    if duration.is_none() {
        Ok(now.py().None().into_bound(now.py()))
    } else {
        duration.call_method1("add_to", (now,))
    }
}

pub(super) fn recorded_view<'py>(
    runtime: &Bound<'py, PyAny>,
    history: &Bound<'py, PyAny>,
    models: &[Bound<'py, PyAny>],
) -> PyResult<Bound<'py, PyAny>> {
    let py = runtime.py();
    let movement = history.getattr("move")?;
    let created = history.getattr("created")?;
    let mut reused = py.None().into_bound(py);
    for item in models {
        if relation(&item.getattr("destination")?)?
            .call_method1("matches", (history.getattr("old")?,))?
            .is_truthy()?
        {
            reused = item.getattr("name")?;
            break;
        }
    }
    model(
        py,
        "OldNameView",
        &[
            ("destination_model", movement.getattr("destination_model")?),
            ("old", location(runtime, &history.getattr("old")?)?),
            ("new", location(runtime, &history.getattr("new")?)?),
            (
                "expires_at",
                if created.is_none() {
                    py.None().into_bound(py)
                } else {
                    created.getattr("expires_at")?
                },
            ),
            (
                "column_aliases",
                if created.is_none() {
                    pyo3::types::PyTuple::empty(py).into_any()
                } else {
                    created.getattr("column_aliases")?
                },
            ),
            ("migration_event_id", movement.getattr("event_id")?),
            ("target_name", movement.getattr("target_name")?),
            ("name_reused_by", reused),
        ],
    )
}
