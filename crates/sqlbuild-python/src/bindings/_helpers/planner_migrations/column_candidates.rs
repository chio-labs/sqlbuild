//! Gather live candidate evidence without changing adapter inspection ownership.

use crate::bindings::_helpers::compile_driver::python_calls::KeywordArguments;
use crate::bindings::_helpers::planner_migrations::column_objects::{
    config, definition_hash, lower, native,
};
use crate::bindings::_helpers::planner_migrations::models::ColumnCandidate;
use crate::bindings::_helpers::records::ids::NativeAttr;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyTuple};

pub(super) fn candidates<'py>(
    args: &KeywordArguments<'py>,
    dialect: &Bound<'py, PyAny>,
) -> PyResult<Vec<ColumnCandidate<'py>>> {
    let scope = args.value("scope")?;
    let snapshot = args.value("snapshot")?;
    let py = scope.py();
    let mut result: Vec<ColumnCandidate<'py>> = Vec::new();
    for key in scope.getattr("execution_order")?.try_iter()? {
        let key = key?;
        if !scope.getattr("selected_keys")?.contains(&key)?
            || !key.getattr("resource_type")?.eq("model")?
        {
            continue;
        }
        let model = scope
            .getattr("models_by_name")?
            .call_method1("get", (key.getattr("name")?,))?;
        if model.is_none() {
            continue;
        }
        let materialized = config(&model, "materialized")?;
        if !materialized.eq("incremental")? && !materialized.eq("snapshot")? {
            continue;
        }
        let name = model.getattr("name")?;
        if args.value("full_refresh_model_names")?.contains(&name)?
            || !snapshot.getattr("existing_relations")?.contains(&name)?
        {
            continue;
        }
        let warehouse = snapshot
            .getattr("existing_columns")?
            .call_method1("get", (&name, PyTuple::empty(py)))?;
        let declared = PyDict::new(py);
        let schema = model.getattr("schema_entry")?;
        if !schema.is_none() {
            for column in schema.getattr("columns")?.try_iter()? {
                let column = column?;
                let origin = column.getattr("migrate_from")?;
                if !origin.is_none() {
                    declared.set_item(column.getattr("name")?, origin.call_method0("strip")?)?;
                }
            }
        }
        let fingerprint = snapshot
            .getattr("fingerprints")?
            .getattr("models")?
            .call_method1("get", (&name,))?;
        let changed = !fingerprint.is_none()
            && !fingerprint
                .getattr("definition_hash")?
                .eq(definition_hash(&model, &snapshot)?)?;
        if !warehouse.is_truthy()? || (declared.is_empty() && !changed) {
            continue;
        }
        let by_name = PyDict::new(py);
        for column in warehouse.try_iter()? {
            let column = column?;
            by_name.set_item(lower(&column.getattr("name")?)?, column)?;
        }
        let previous = if changed {
            native(
                py,
                NativeAttr::ParseQueryShape,
                &[
                    ("query_sql", fingerprint.getattr("definition")?),
                    ("dialect", dialect.clone()),
                ],
            )?
        } else {
            py.None().into_bound(py)
        };
        let current = native(
            py,
            NativeAttr::ParseQueryShape,
            &[
                ("query_sql", model.getattr("query_sql")?),
                ("dialect", dialect.clone()),
            ],
        )?;
        result.push(ColumnCandidate {
            model,
            warehouse: by_name,
            declared,
            fingerprint,
            previous,
            current,
        });
    }
    Ok(result)
}

pub(super) fn declared_names<'py>(
    candidate: &ColumnCandidate<'py>,
) -> PyResult<Bound<'py, PyFrozenSet>> {
    let mut names: Vec<String> = Vec::new();
    for (destination, origin) in candidate.declared.iter() {
        names.push(lower(&destination)?);
        names.push(lower(&origin)?);
    }
    PyFrozenSet::new(candidate.model.py(), names)
}
