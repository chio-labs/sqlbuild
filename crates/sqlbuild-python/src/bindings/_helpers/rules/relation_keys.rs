//! Declared unique keys of project relations, derived natively from their key facts.

use std::collections::BTreeMap;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyList, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_rules::sql_quality::main::declared_relation_keys::declared_relation_keys as derive_keys;
use sqlbuild_rules::sql_quality::models::{DeclaredKeyColumn, DeclaredRelation};

const MATERIALIZED_CONFIG: &str = "materialized";
const INCREMENTAL_MODE_CONFIG: &str = "incremental_mode";
const INCREMENTAL_STRATEGY_CONFIG: &str = "incremental_strategy";
const CURSOR_CONFIG: &str = "cursor";
const UNIQUE_KEY_CONFIG: &str = "unique_key";
const UNIQUE_AUDIT_COLUMN_ARGUMENT: &str = "column";
const RELATION_KIND_SEED: &str = "seed";
const RELATION_KIND_SOURCE: &str = "source";

/// `(kind, name, materialized, mode, strategy, cursor, unique key, columns, audits)`.
pub(crate) type RelationKeyRow = (
    String,
    String,
    String,
    String,
    String,
    bool,
    Option<Vec<String>>,
    Vec<(String, Vec<String>, bool)>,
    Vec<(String, Option<String>)>,
);

/// The key row of one relation from its config values and declared column and audit specs.
pub(crate) fn relation_key_row(
    kind: &str,
    name: String,
    values: &Bound<'_, PyDict>,
    declared: Option<(&Bound<'_, PyAny>, &Bound<'_, PyAny>)>,
) -> PyResult<RelationKeyRow> {
    let mut columns: Vec<(String, Vec<String>, bool)> = Vec::new();
    let mut audits: Vec<(String, Option<String>)> = Vec::new();
    if let Some((declared_columns, declared_audits)) = declared {
        for column in declared_columns.try_iter()? {
            let column: Bound<'_, PyAny> = column?;
            let nullable: Option<Bound<'_, PyAny>> = column.getattr_opt("nullable")?;
            columns.push((
                column.getattr("name")?.str()?.extract()?,
                audit_names(column.getattr_opt("audits")?)?,
                nullable.is_some_and(|value| value.is(PyBool::new(column.py(), false))),
            ));
        }
        for audit in declared_audits.try_iter()? {
            let audit: Bound<'_, PyAny> = audit?;
            let argument: Option<Bound<'_, PyAny>> = audit
                .getattr("arguments")?
                .downcast::<PyDict>()?
                .get_item(UNIQUE_AUDIT_COLUMN_ARGUMENT)?;
            audits.push((
                audit.getattr("definition_name")?.extract()?,
                argument
                    .filter(pyo3::types::PyAnyMethods::is_instance_of::<PyString>)
                    .map(|value| value.extract())
                    .transpose()?,
            ));
        }
    }
    Ok((
        kind.to_owned(),
        name,
        config_text(values, MATERIALIZED_CONFIG)?,
        config_text(values, INCREMENTAL_MODE_CONFIG)?,
        config_text(values, INCREMENTAL_STRATEGY_CONFIG)?,
        values
            .get_item(CURSOR_CONFIG)?
            .is_some_and(|value| value.is_truthy().unwrap_or(false)),
        unique_key(values)?,
        columns,
        audits,
    ))
}

fn audit_names(audits: Option<Bound<'_, PyAny>>) -> PyResult<Vec<String>> {
    let Some(audits) = audits.filter(|audits| !audits.is_none()) else {
        return Ok(Vec::new());
    };
    let mut names: Vec<String> = Vec::new();
    for audit in audits.try_iter()? {
        names.push(audit?.getattr("definition_name")?.extract()?);
    }
    Ok(names)
}

/// `str(values.get(key, ""))`.
fn config_text(values: &Bound<'_, PyDict>, key: &str) -> PyResult<String> {
    match values.get_item(key)? {
        Some(value) => value.str()?.extract(),
        None => Ok(String::new()),
    }
}

/// `unique_key` as a name list, when it is a name or a non-empty list or tuple of names.
fn unique_key(values: &Bound<'_, PyDict>) -> PyResult<Option<Vec<String>>> {
    let Some(value) = values.get_item(UNIQUE_KEY_CONFIG)? else {
        return Ok(None);
    };
    if value.is_instance_of::<PyString>() {
        return Ok(Some(vec![value.extract()?]));
    }
    if !(value.is_instance_of::<PyList>() || value.is_instance_of::<PyTuple>()) {
        return Ok(None);
    }
    let mut names: Vec<String> = Vec::new();
    for item in value.try_iter()? {
        let item: Bound<'_, PyAny> = item?;
        if !item.is_instance_of::<PyString>() {
            return Ok(None);
        }
        names.push(item.str()?.extract()?);
    }
    Ok(Some(names))
}

/// The key row of a seed, source or hand-built model from its config values and schema entry.
#[pyfunction(name = "relation_key_row")]
#[pyo3(signature = (kind, name, values, entry))]
fn entry_relation_key_row(
    kind: &str,
    name: String,
    values: &Bound<'_, PyDict>,
    entry: &Bound<'_, PyAny>,
) -> PyResult<RelationKeyRow> {
    if entry.is_none() {
        return relation_key_row(kind, name, values, None);
    }
    let columns: Bound<'_, PyAny> = declared_specs(entry, "columns")?;
    let audits: Bound<'_, PyAny> = declared_specs(entry, "audits")?;
    relation_key_row(kind, name, values, Some((&columns, &audits)))
}

/// `getattr(entry, name, None) or ()`.
fn declared_specs<'py>(entry: &Bound<'py, PyAny>, name: &str) -> PyResult<Bound<'py, PyAny>> {
    match entry.getattr_opt(name)? {
        Some(specs) if specs.is_truthy()? => Ok(specs),
        _ => Ok(PyTuple::empty(entry.py()).into_any()),
    }
}

/// Keys that prove one row per key, by `kind:name` identity, from model rows, seeds and sources.
#[pyfunction]
#[pyo3(signature = (*, model_rows, seeds, sources))]
fn declared_relation_keys<'py>(
    py: Python<'py>,
    model_rows: &Bound<'py, PyAny>,
    seeds: &Bound<'py, PyAny>,
    sources: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let mut rows: Vec<RelationKeyRow> = Vec::new();
    for row in model_rows.try_iter()? {
        rows.push(row?.extract()?);
    }
    for (kind, entries) in [(RELATION_KIND_SEED, seeds), (RELATION_KIND_SOURCE, sources)] {
        for entry in entries.try_iter()? {
            let entry: Bound<'py, PyAny> = entry?;
            let name: String = entry.getattr("name")?.extract()?;
            rows.push(entry_relation_key_row(
                kind,
                name,
                &PyDict::new(py),
                &entry,
            )?);
        }
    }
    let relations: Vec<DeclaredRelation> = rows.into_iter().map(declared_relation).collect();
    let keys: BTreeMap<String, Vec<Vec<String>>> = py.detach(|| derive_keys(&relations));
    let found: Bound<'py, PyDict> = PyDict::new(py);
    for (identity, unique_keys) in keys {
        let mut tuples: Vec<Bound<'py, PyTuple>> = Vec::with_capacity(unique_keys.len());
        for key in unique_keys {
            tuples.push(PyTuple::new(py, key)?);
        }
        found.set_item(identity, PyTuple::new(py, tuples)?)?;
    }
    Ok(found)
}

/// Declared keys of a compiled project's models, seeds and sources.
#[pyfunction]
fn compiled_relation_keys<'py>(project: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = project.py();
    let mut model_rows: Vec<Bound<'py, PyAny>> = Vec::new();
    for model in project.getattr("models")?.try_iter()? {
        model_rows.push(model?.getattr("relation_key_row")?);
    }
    let mut seeds: Vec<Bound<'py, PyAny>> = Vec::new();
    for seed in project.getattr("seeds")?.try_iter()? {
        seeds.push(seed?.getattr("schema_entry")?);
    }
    let mut sources: Vec<Bound<'py, PyAny>> = Vec::new();
    for source in project.getattr("sources")?.try_iter()? {
        sources.push(source?.getattr("source_entry")?);
    }
    declared_relation_keys(
        py,
        PyTuple::new(py, model_rows)?.as_any(),
        PyTuple::new(py, seeds)?.as_any(),
        PyTuple::new(py, sources)?.as_any(),
    )
}

fn declared_relation(row: RelationKeyRow) -> DeclaredRelation {
    let (kind, name, materialized, mode, strategy, has_cursor, unique_key, columns, audits) = row;
    DeclaredRelation {
        kind,
        name,
        materialized,
        incremental_mode: mode,
        incremental_strategy: strategy,
        has_cursor,
        unique_key,
        columns: columns
            .into_iter()
            .map(|(name, audits, not_nullable)| DeclaredKeyColumn {
                name,
                audits,
                not_nullable,
            })
            .collect(),
        audits,
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(entry_relation_key_row, module)?)?;
    module.add_function(wrap_pyfunction!(declared_relation_keys, module)?)?;
    module.add_function(wrap_pyfunction!(compiled_relation_keys, module)?)
}
