//! Project column renames onto the existing snapshot and redirect cursor reads.

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::planner_migrations::column_objects::{
    config, definition_hash, lower, model, native, replace,
};
use crate::bindings::_helpers::planner_migrations::constants::PLANNING;
use crate::bindings::_helpers::planner_migrations::models::ColumnCandidate;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};

pub(super) fn overlay<'py>(
    snapshot: &Bound<'py, PyAny>,
    candidates: &[ColumnCandidate<'py>],
    entries: &[Bound<'py, PyAny>],
    inputs: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    if entries.is_empty() {
        return Ok(snapshot.clone());
    }
    let py = snapshot.py();
    let columns =
        imported(py, "builtins", "dict")?.call1((snapshot.getattr("existing_columns")?,))?;
    let stored = snapshot.getattr("fingerprints")?;
    let fingerprints = imported(py, "builtins", "dict")?.call1((stored.getattr("models")?,))?;
    for candidate in candidates {
        let name = candidate.model.getattr("name")?;
        let renames = PyDict::new(py);
        let pending = PyDict::new(py);
        let mut blocked = false;
        for entry in entries {
            if !entry.getattr("model_name")?.eq(&name)? {
                continue;
            }
            blocked |= entry.getattr("blocks_build")?.is_truthy()?
                || entry.getattr("origin_missing")?.is_truthy()?;
            renames.set_item(
                entry.getattr("origin_column")?,
                entry.getattr("destination_column")?,
            )?;
            if entry.getattr("decision")?.getattr("renames")?.is_truthy()? {
                pending.set_item(
                    lower(&entry.getattr("origin_column")?)?,
                    entry.getattr("destination_column")?,
                )?;
            }
        }
        if renames.is_empty() || blocked {
            continue;
        }
        let mut renamed: Vec<Bound<'py, PyAny>> = Vec::new();
        for column in snapshot
            .getattr("existing_columns")?
            .call_method1("get", (&name, PyTuple::empty(py)))?
            .try_iter()?
        {
            let column = column?;
            let old = column.getattr("name")?;
            let new = pending.get_item(lower(&old)?)?.unwrap_or(old);
            renamed.push(replace(&column, &[("name", new)])?);
        }
        columns.set_item(&name, PyTuple::new(py, renamed)?)?;
        if !candidate.fingerprint.is_none()
            && !candidate.previous.is_none()
            && !candidate.current.is_none()
            && native(
                py,
                "renames_explain_change",
                &[
                    ("previous", candidate.previous.clone()),
                    ("current", candidate.current.clone()),
                    ("renames", renames.into_any()),
                    ("input_columns", inputs.clone()),
                ],
            )?
            .is_truthy()?
        {
            fingerprints.set_item(
                &name,
                replace(
                    &candidate.fingerprint,
                    &[
                        ("definition", candidate.model.getattr("query_sql")?),
                        (
                            "definition_hash",
                            definition_hash(&candidate.model, snapshot)?,
                        ),
                    ],
                )?,
            )?;
        }
    }
    replace(
        snapshot,
        &[
            ("existing_columns", columns),
            (
                "fingerprints",
                model(
                    py,
                    "WarehouseFingerprints",
                    &[
                        ("models", fingerprints),
                        ("functions", stored.getattr("functions")?),
                        ("seeds", stored.getattr("seeds")?),
                        ("python_nodes", stored.getattr("python_nodes")?),
                    ],
                )?,
            ),
        ],
    )
}

pub(super) fn cursors<'py>(
    args: &KeywordArguments<'py>,
    snapshot: Bound<'py, PyAny>,
    entries: &[Bound<'py, PyAny>],
) -> PyResult<Bound<'py, PyAny>> {
    let py = snapshot.py();
    let scope = args.value("scope")?;
    let models = scope.getattr("models_by_name")?;
    let origins = PyDict::new(py);
    for entry in entries {
        let name = entry.getattr("model_name")?;
        let model = models.call_method1("get", (&name,))?;
        let cursor = if model.is_truthy()? {
            config(&model, "cursor")?
        } else {
            py.None().into_bound(py)
        };
        if entry.getattr("decision")?.getattr("renames")?.is_truthy()?
            && !cursor.is_none()
            && lower(&cursor)? == lower(&entry.getattr("destination_column")?)?
        {
            origins.set_item(name, entry.getattr("origin_column")?)?;
        }
    }
    if origins.is_empty() {
        return Ok(snapshot);
    }
    let targets = PyDict::new(py);
    for (name, _) in origins.iter() {
        let physical = args
            .value("physical_relations")?
            .call_method1("get", (&name,))?;
        let target = if physical.is_truthy()? {
            physical
        } else {
            let qualified = models
                .get_item(&name)?
                .getattr("destination")?
                .getattr("qualified_name")?;
            if qualified.is_truthy()? {
                qualified
            } else {
                name.clone()
            }
        };
        targets.set_item(name, target)?;
    }
    let redirected = call_with(
        &imported(py, PLANNING, "redirected_cursor_snapshots")?,
        &[
            ("runtime", args.value("runtime")?),
            ("scope", scope),
            (
                "existing_relations",
                snapshot.getattr("existing_relations")?,
            ),
            ("target_relations", targets.into_any()),
            ("overrides", args.value("overrides")?),
            ("deferral", args.value("deferral")?),
            ("origin_cursor_columns", origins.into_any()),
        ],
    )?;
    let cursors =
        imported(py, "builtins", "dict")?.call1((snapshot.getattr("cursor_snapshots")?,))?;
    cursors.call_method1("update", (redirected,))?;
    replace(&snapshot, &[("cursor_snapshots", cursors)])
}
