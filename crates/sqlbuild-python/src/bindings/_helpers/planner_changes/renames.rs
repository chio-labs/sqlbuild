//! Model renames that downstream `__ref` names may have been rewritten for.

use std::collections::BTreeSet;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PySet, PySetMethods, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

use sqlbuild_analysis::planner_changes::main::origin_reference_names::origin_reference_names;
use sqlbuild_analysis::planner_changes::models::{NameSpan, RenameCandidate};
use sqlbuild_rules::lint_text::main::neutralize_interpolation::neutralize_interpolation;

use crate::bindings::_helpers::boundary::panics::value_error;
use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::planner_changes::results::MODELS_MODULE;
use crate::bindings::_helpers::planner_identity::hashing::model_query_hash;

const NATIVE_MODULE: &str = "sqlbuild._native";
const REFERENCE_TYPES_MODULE: &str = "sqlbuild.compiler.references.types";
const GENERIC_DIALECT: &str = "generic";
const FINAL_NEWLINE: &str = "\n";

const REF_CALL_PREFIX: &str = "__ref";

/// The rename mapping under which the model query hashes to its recorded definition.
pub(crate) fn origin_names(
    (query_sql, fingerprint): (String, &Bound<'_, PyAny>),
    renames: &Bound<'_, PyAny>,
    (recorded_hash, dialect): (&str, &Bound<'_, PyAny>),
) -> PyResult<Option<Vec<(String, String)>>> {
    let py: Python<'_> = fingerprint.py();
    let recorded_at: Bound<'_, PyAny> = utc(&fingerprint.getattr("ts")?)?;
    let mut candidates: Vec<RenameCandidate> = Vec::new();
    for rename in renames.try_iter()? {
        let rename: Bound<'_, PyAny> = rename?;
        let renamed_at: Bound<'_, PyAny> = rename.getattr("recorded_at")?;
        candidates.push(RenameCandidate {
            new_name: rename.getattr("new_name")?.extract()?,
            origin_name: rename.getattr("origin_name")?.extract()?,
            applies: renamed_at.is_none() || recorded_at.lt(utc(&renamed_at)?)?,
        });
    }
    let dialect_name: String = dialect
        .extract::<Option<String>>()?
        .filter(|name| !name.is_empty())
        .unwrap_or_else(|| GENERIC_DIALECT.to_owned());
    let mut spans = |names: &BTreeSet<String>| ref_name_spans(&query_sql, &dialect_name, names);
    let compute_hash: Bound<'_, PyAny> = imported(py, NATIVE_MODULE, "compute_query_hash")?;
    let mut query_hash = |text: &str| -> PyResult<String> {
        call_with(
            &compute_hash,
            &[
                ("query_sql", PyString::new(py, text).into_any()),
                ("dialect", dialect.clone()),
            ],
        )?
        .extract()
    };
    origin_reference_names(
        (&query_sql, recorded_hash),
        &candidates,
        (&mut spans, &mut query_hash),
    )
}

fn ref_name_spans(
    query_sql: &str,
    dialect: &str,
    names: &BTreeSet<String>,
) -> PyResult<Vec<NameSpan>> {
    let neutralized = neutralize_interpolation(query_sql, dialect, false).map_err(value_error)?;
    let mut spans: Vec<NameSpan> = Vec::new();
    for site in neutralized.sites {
        let Some((offset, name)) = ref_call_name(&site.original_text) else {
            continue;
        };
        if !names.contains(name) {
            continue;
        }
        let start: usize = site.original_start + site.original_text[..offset].chars().count();
        spans.push(NameSpan {
            start,
            end: start + name.chars().count(),
            name: name.to_owned(),
        });
    }
    Ok(spans)
}

/// The byte offset and name of a whole `__ref('name')` or `__ref("name")` call.
fn ref_call_name(text: &str) -> Option<(usize, &str)> {
    let rest: &str = text.strip_prefix(REF_CALL_PREFIX)?.trim_start();
    let rest: &str = rest.strip_prefix('(')?.trim_start();
    let quote: char = rest
        .chars()
        .next()
        .filter(|quote| matches!(quote, '\'' | '"'))?;
    let body: &str = &rest[1..];
    let length: usize = body.find(['\'', '"'])?;
    let name: &str = &body[..length];
    let tail: &str = body[length..].strip_prefix(quote)?.trim_start();
    let tail: &str = tail.strip_prefix(')')?;
    if name.is_empty() || !(tail.is_empty() || tail == FINAL_NEWLINE) {
        return None;
    }
    Some((text.len() - body.len(), name))
}

/// `value` in UTC; a naive value is taken as UTC.
fn utc<'py>(value: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = value.py();
    let zone: Bound<'py, PyAny> = imported(py, "datetime", "UTC")?;
    if value.getattr("tzinfo")?.is_none() || value.call_method0("utcoffset")?.is_none() {
        return call_with(&value.getattr("replace")?, &[("tzinfo", zone)]);
    }
    value.call_method1("astimezone", (zone,))
}

/// The rename mapping under which `query_sql` hashes to the recorded definition, or `None`.
#[pyfunction(name = "origin_reference_names")]
#[pyo3(signature = (*, query_sql, recorded, renames, dialect))]
fn origin_reference_names_of<'py>(
    query_sql: String,
    recorded: &Bound<'py, PyAny>,
    renames: &Bound<'py, PyAny>,
    dialect: &Bound<'py, PyAny>,
) -> PyResult<Option<Bound<'py, PyDict>>> {
    let py: Python<'py> = recorded.py();
    let recorded_hash: String = recorded.getattr("definition_hash")?.extract()?;
    let Some(mapping) = origin_names((query_sql, recorded), renames, (&recorded_hash, dialect))?
    else {
        return Ok(None);
    };
    let result: Bound<'py, PyDict> = PyDict::new(py);
    for (name, origin) in mapping {
        result.set_item(name, origin)?;
    }
    Ok(Some(result))
}

/// This plan's renames plus recorded renames, read only when a selected query that references models changed.
#[pyfunction]
#[pyo3(signature = (**options))]
fn plan_reference_renames<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "plan_reference_renames",
        options,
        (
            &[
                "runtime", "scope", "snapshot", "state", "schemas", "planned",
            ],
            &[],
        ),
    )?;
    let (runtime, scope, snapshot) = (
        arguments.value("runtime")?,
        arguments.value("scope")?,
        arguments.value("snapshot")?,
    );
    let (state, schemas, planned) = (
        arguments.value("state")?,
        arguments.value("schemas")?,
        arguments.value("planned")?,
    );
    let (runtime, scope, snapshot) = (&runtime, &scope, &snapshot);
    if !changed_referencing_query(scope, snapshot)? {
        return Ok(PyTuple::empty(py));
    }
    let state_schemas: Bound<'py, PyAny> = snapshot.getattr("migration_state_schemas")?;
    let inspected: Bound<'py, PySet> = PySet::empty(py)?;
    for schema in schemas.try_iter()? {
        let schema: Bound<'py, PyAny> = schema?;
        if state_schemas.contains(schema.call_method0("lower")?)? {
            inspected.add(schema)?;
        }
    }
    call_with(
        &state.getattr("inspect_migration_events")?,
        &[("schemas", inspected.into_any())],
    )?;
    let target_name: Bound<'py, PyAny> = runtime
        .getattr("project")?
        .getattr("effective_target_name")?;
    let rename_class: Bound<'py, PyAny> = imported(py, MODELS_MODULE, "ReferenceRename")?;
    let mut renames: Vec<Bound<'py, PyAny>> = Vec::new();
    for item in planned.call_method0("items")?.try_iter()? {
        let item: Bound<'py, PyAny> = item?;
        let (new_name, origin_name) = (item.get_item(0)?, item.get_item(1)?);
        if new_name.ne(&origin_name)? {
            renames.push(call_with(
                &rename_class,
                &[("new_name", new_name), ("origin_name", origin_name)],
            )?);
        }
    }
    for event in state.getattr("events")?.try_iter()? {
        let event: Bound<'py, PyAny> = event?;
        let event_target: Bound<'py, PyAny> = event.getattr("target_name")?;
        let origin: Bound<'py, PyAny> = event.getattr("origin_model")?;
        let destination: Bound<'py, PyAny> = event.getattr("destination_model")?;
        if (event_target.is_none() || event_target.eq(&target_name)?)
            && !origin.is_none()
            && origin.ne(&destination)?
        {
            renames.push(call_with(
                &rename_class,
                &[
                    ("new_name", destination),
                    ("origin_name", origin),
                    ("recorded_at", event.getattr("created_at")?),
                ],
            )?);
        }
    }
    PyTuple::new(py, renames)
}

fn changed_referencing_query(
    scope: &Bound<'_, PyAny>,
    snapshot: &Bound<'_, PyAny>,
) -> PyResult<bool> {
    let py: Python<'_> = scope.py();
    let models_by_name: Bound<'_, PyAny> = scope.getattr("models_by_name")?;
    let mut selected: Vec<Bound<'_, PyAny>> = Vec::new();
    for key in scope.getattr("selected_keys")?.try_iter()? {
        let model: Bound<'_, PyAny> =
            models_by_name.call_method1("get", (key?.getattr("name")?,))?;
        if !model.is_none() {
            selected.push(model);
        }
    }
    let recorded_models: Bound<'_, PyAny> = snapshot.getattr("fingerprints")?.getattr("models")?;
    let ref_kind: Bound<'_, PyAny> =
        imported(py, REFERENCE_TYPES_MODULE, "SqlReferenceKind")?.getattr("REF")?;
    let dialect: Option<String> = snapshot.getattr("column_dialect")?.extract()?;
    for model in selected {
        let recorded: Bound<'_, PyAny> =
            recorded_models.call_method1("get", (model.getattr("name")?,))?;
        if recorded.is_none() {
            continue;
        }
        let mut references_models: bool = false;
        for reference in model.getattr("references")?.try_iter()? {
            if reference?.getattr("ref_kind")?.eq(&ref_kind)? {
                references_models = true;
                break;
            }
        }
        if references_models
            && model_query_hash(
                py,
                &model.getattr("name")?.extract::<String>()?,
                (
                    &model.getattr("query_sql")?.extract::<String>()?,
                    dialect.as_deref(),
                ),
            )? != recorded.getattr("definition_hash")?.extract::<String>()?
        {
            return Ok(true);
        }
    }
    Ok(false)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(plan_reference_renames, module)?)?;
    module.add_function(wrap_pyfunction!(origin_reference_names_of, module)?)
}
