//! Materialize column decisions from native proofs and live evidence.

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::planner_migrations::column_candidates::declared_names;
use crate::bindings::_helpers::planner_migrations::column_objects::{
    lower, model, native, replace,
};
use crate::bindings::_helpers::planner_migrations::constants::{AUTOMATIC, DONE, MIGRATION_TYPES};
use crate::bindings::_helpers::planner_migrations::models::{CheckedColumns, ColumnCandidate};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyListMethods, PyTuple};
use sqlbuild_analysis::planner_migrations::main::column_decision::column_decision;

pub(super) fn decide<'py>(
    runtime: &Bound<'py, PyAny>,
    candidate: &ColumnCandidate<'py>,
    events: &Bound<'py, PyAny>,
    inputs: &Bound<'py, PyAny>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py = runtime.py();
    let mut pairs: Vec<(Bound<'py, PyAny>, Bound<'py, PyAny>, &str)> = Vec::new();
    let declared = PyDict::new(py);
    for (destination, origin) in candidate.declared.iter() {
        declared.set_item(&origin, &destination)?;
        pairs.push((origin, destination, "manual"));
    }
    if !candidate.previous.is_none() && !candidate.current.is_none() {
        let detected = native(
            py,
            "identical_renames",
            &[
                ("previous", candidate.previous.clone()),
                ("current", candidate.current.clone()),
                ("excluded", declared_names(candidate)?.into_any()),
                ("declared", declared.into_any()),
                ("input_columns", inputs.clone()),
            ],
        )?;
        for pair in detected.try_iter()? {
            let pair = pair?;
            pairs.push((pair.get_item(0)?, pair.get_item(1)?, "automatic"));
        }
    }
    let mut outputs: Vec<String> = Vec::new();
    if !candidate.current.is_none() {
        for projection in candidate.current.getattr("projections")?.try_iter()? {
            outputs.push(projection?.getattr("key")?.extract::<String>()?);
        }
    } else {
        let inferred = candidate.model.getattr("inferred_columns")?;
        if !inferred.is_none() {
            for column in inferred.try_iter()? {
                outputs.push(lower(&column?.getattr("name")?)?);
            }
        }
    }
    let relation = imported(
        py,
        "sqlbuild.compiler.migrations.main.relation_for_location",
        "migration_relation_for_location",
    )?
    .call1((candidate.model.getattr("destination")?,))?;
    let newest_event = imported(
        py,
        "sqlbuild.compiler.migrations.main._newest_column_event",
        "newest_column_migration_event_mentioning",
    )?;
    let mut entries: Vec<Bound<'py, PyAny>> = Vec::new();
    for (origin_name, destination, discovery) in pairs {
        let origin_key = lower(&origin_name)?;
        let origin = candidate.warehouse.get_item(&origin_key)?;
        let has_destination = candidate.warehouse.contains(lower(&destination)?)?;
        let newest = call_with(
            &newest_event,
            &[
                ("events", events.clone()),
                ("relation", relation.clone()),
                ("origin_column", origin_name.clone()),
                ("destination_column", destination.clone()),
            ],
        )?;
        let recorded = !newest.is_none()
            && call_with(
                &newest.getattr("renamed")?,
                &[
                    ("origin_column", origin_name.clone()),
                    ("destination_column", destination.clone()),
                ],
            )?
            .is_truthy()?;
        let decision_name = column_decision(
            recorded,
            (origin.is_some(), has_destination),
            outputs.contains(&origin_key),
        );
        let decision =
            imported(py, MIGRATION_TYPES, "ColumnMigrationDecision")?.call1((decision_name,))?;
        if discovery == AUTOMATIC && decision.getattr("blocks_build")?.is_truthy()? {
            continue;
        }
        let done = decision_name == DONE && !newest.is_none();
        entries.push(model(
            py,
            "ColumnMigrationPlanEntry",
            &[
                ("model_name", candidate.model.getattr("name")?),
                ("destination", candidate.model.getattr("destination")?),
                (
                    "origin_column",
                    if let Some(origin) = origin {
                        origin.getattr("name")?
                    } else {
                        origin_name
                    },
                ),
                ("destination_column", destination),
                (
                    "discovery",
                    imported(py, MIGRATION_TYPES, "MigrationDiscovery")?.call1((discovery,))?,
                ),
                ("decision", decision),
                (
                    "target_name",
                    if done {
                        newest.getattr("target_name")?
                    } else {
                        runtime
                            .getattr("project")?
                            .getattr("effective_target_name")?
                    },
                ),
                (
                    "completed_at",
                    if done {
                        newest.getattr("created_at")?
                    } else {
                        py.None().into_bound(py)
                    },
                ),
            ],
        )?);
    }
    Ok(entries)
}

pub(super) fn checked<'py>(
    runtime: &Bound<'py, PyAny>,
    candidate: &ColumnCandidate<'py>,
    entries: Vec<Bound<'py, PyAny>>,
    physical: &Bound<'py, PyAny>,
) -> PyResult<CheckedColumns<'py>> {
    let py = runtime.py();
    let mut pending = false;
    for entry in &entries {
        pending |= entry.getattr("decision")?.getattr("renames")?.is_truthy()?;
    }
    if !pending {
        return Ok(CheckedColumns {
            entries,
            warnings: Vec::new(),
        });
    }
    let destination = candidate.model.getattr("destination")?;
    let qualified = destination.getattr("qualified_name")?;
    let relation = if physical.is_truthy()? {
        physical.clone()
    } else if qualified.is_truthy()? {
        qualified
    } else {
        destination.getattr("name")?
    };
    let reason = call_with(
        &runtime
            .getattr("adapter")?
            .getattr("column_rename_unavailable_reason")?,
        &[
            ("connection", runtime.getattr("connection")?),
            ("destination", relation),
        ],
    )?;
    if reason.is_none() {
        return Ok(CheckedColumns {
            entries,
            warnings: Vec::new(),
        });
    }
    let mut checked: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut warnings: Vec<Bound<'py, PyAny>> = Vec::new();
    for entry in entries {
        if !entry.getattr("decision")?.getattr("renames")?.is_truthy()? {
            checked.push(entry);
        } else if entry.getattr("discovery")?.eq("manual")? {
            checked.push(replace(
                &entry,
                &[
                    (
                        "decision",
                        imported(py, MIGRATION_TYPES, "ColumnMigrationDecision")?
                            .getattr("UNSUPPORTED")?,
                    ),
                    ("message", reason.clone()),
                ],
            )?);
        } else {
            warnings.push(super::column_warnings::unavailable(
                &entry,
                &reason.extract::<String>()?,
            )?);
        }
    }
    Ok(CheckedColumns {
        entries: checked,
        warnings,
    })
}

pub(super) fn hints<'py>(
    candidate: &ColumnCandidate<'py>,
    entries: &[Bound<'py, PyAny>],
) -> PyResult<Bound<'py, PyAny>> {
    let py = candidate.model.py();
    if candidate.previous.is_none() || candidate.current.is_none() {
        return Ok(PyTuple::empty(py).into_any());
    }
    let excluded = declared_names(candidate)?.call_method0("copy")?;
    let claimed = PyDict::new(py);
    for entry in entries {
        claimed.set_item(lower(&entry.getattr("origin_column")?)?, py.None())?;
        claimed.set_item(lower(&entry.getattr("destination_column")?)?, py.None())?;
    }
    native(
        py,
        "rename_hints",
        &[
            ("model_name", candidate.model.getattr("name")?),
            ("previous", candidate.previous.clone()),
            ("current", candidate.current.clone()),
            ("excluded", excluded.call_method1("union", (claimed,))?),
            (
                "live_columns",
                PyFrozenSet::new(py, candidate.warehouse.keys().iter())?.into_any(),
            ),
        ],
    )
}
