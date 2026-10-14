//! Project inherited fingerprints and live relation facts before normal planning.

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::planner_migrations::column_objects::{config, model, replace};
use crate::bindings::_helpers::planner_migrations::constants::PLANNING;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods};

pub(super) fn overlay<'py>(
    args: &KeywordArguments<'py>,
    state: &Bound<'py, PyAny>,
    entries: &[Bound<'py, PyAny>],
    handovers: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyAny>> {
    let snapshot = args.value("snapshot")?;
    if handovers.is_empty() {
        return Ok(snapshot);
    }
    let runtime = args.value("runtime")?;
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
    let gathered = call_with(
        &imported(py, PLANNING, "redirected_cursor_snapshots")?,
        &[
            ("runtime", runtime),
            ("scope", args.value("scope")?),
            ("existing_relations", relations.clone().into_any()),
            ("target_relations", redirected.into_any()),
            ("overrides", args.value("overrides")?),
            ("deferral", args.value("deferral")?),
        ],
    )?;
    cursors.call_method1("update", (gathered,))?;
    replace(
        &snapshot,
        &[
            ("existing_relations", relations.into_any()),
            ("existing_columns", columns.into_any()),
            (
                "fingerprints",
                model(
                    py,
                    "WarehouseFingerprints",
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
    for item in runtime.getattr("project")?.getattr("models")?.try_iter()? {
        let item = item?;
        if item.getattr("name")?.eq(name)? {
            return Ok(config(&item, "materialized")?.eq("incremental")?
                && !config(&item, "cursor")?.is_none());
        }
    }
    Ok(false)
}
