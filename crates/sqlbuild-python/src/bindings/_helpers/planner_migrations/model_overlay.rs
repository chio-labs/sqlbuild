//! Project inherited fingerprints and live relation facts before normal planning.

use crate::bindings::_helpers::planner_migrations::column_objects::native;
use crate::bindings::_helpers::planner_migrations::column_objects::{config, replace};
use crate::bindings::_helpers::planner_migrations::models::MigrationPhase;
use crate::bindings::_helpers::planner_phases::runtime::runtime_field;
use crate::bindings::_helpers::records::ids::RecordId;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods};

pub(super) fn overlay<'py>(
    phase: &MigrationPhase<'py>,
    state: &Bound<'py, PyAny>,
    entries: &[Bound<'py, PyAny>],
    handovers: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyAny>> {
    let snapshot = phase.snapshot.clone();
    if handovers.is_empty() {
        return Ok(snapshot);
    }
    let runtime = phase.runtime.clone();
    let py = runtime.py();
    let relations = snapshot
        .getattr("existing_relations")?
        .cast_into::<PyDict>()?
        .copy()?;
    let columns = snapshot
        .getattr("existing_columns")?
        .cast_into::<PyDict>()?
        .copy()?;
    let fingerprints = snapshot.getattr("fingerprints")?;
    let models = fingerprints
        .getattr("models")?
        .cast_into::<PyDict>()?
        .copy()?;
    let redirected = PyDict::new(py);
    for entry in entries {
        let name = entry.getattr("model_name")?;
        let Some(handover) = handovers.get_item(&name)? else {
            continue;
        };
        if handover.is_none() {
            models.call_method1("pop", (&name, py.None()))?;
        } else {
            models.set_item(&name, handover)?;
        }
        if !entry
            .getattr("decision")?
            .getattr("moves_data")?
            .is_truthy()?
        {
            continue;
        }
        let origin = entry.getattr("origin")?;
        let origin_relation = state.call_method1("relation", (&origin,))?;
        if origin_relation.is_none() {
            continue;
        }
        let destination = entry.getattr("destination")?;
        let transient = entry.getattr("stage_is_transient")?;
        relations.set_item(
            &name,
            replace(
                &origin_relation,
                &[
                    ("database", destination.getattr("database")?),
                    ("schema", destination.getattr("schema")?),
                    ("name", destination.getattr("name")?),
                    (
                        "is_transient",
                        if transient.is_none() {
                            origin_relation.getattr("is_transient")?
                        } else {
                            transient
                        },
                    ),
                ],
            )?,
        )?;
        columns.set_item(&name, state.call_method1("relation_columns", (&origin,))?)?;
        let qualified = origin.getattr("qualified_name")?;
        if !qualified.is_none() && cursor_enabled(&runtime, &name)? {
            redirected.set_item(name, qualified)?;
        }
    }
    let cursors = snapshot
        .getattr("cursor_snapshots")?
        .cast_into::<PyDict>()?
        .copy()?;
    let gathered = super::planning_boundary::redirected_cursor_snapshots(
        phase,
        (relations.clone().into_any(), redirected.into_any()),
        None,
    )?;
    cursors.call_method1("update", (gathered,))?;
    replace(
        &snapshot,
        &[
            ("existing_relations", relations.into_any()),
            ("existing_columns", columns.into_any()),
            (
                "fingerprints",
                native(
                    py,
                    RecordId::WarehouseFingerprints,
                    &[
                        ("models", models.into_any()),
                        ("functions", fingerprints.getattr("functions")?),
                        ("seeds", fingerprints.getattr("seeds")?),
                        ("python_nodes", fingerprints.getattr("python_nodes")?),
                    ],
                )?,
            ),
            ("cursor_snapshots", cursors.into_any()),
        ],
    )
}

fn cursor_enabled(runtime: &Bound<'_, PyAny>, name: &Bound<'_, PyAny>) -> PyResult<bool> {
    for item in runtime_field(runtime, |runtime| &runtime.project)?
        .getattr("models")?
        .try_iter()?
    {
        let item = item?;
        if item.getattr("name")?.eq(name)? {
            return Ok(config(&item, "materialized")?.eq("incremental")?
                && !config(&item, "cursor")?.is_none());
        }
    }
    Ok(false)
}
