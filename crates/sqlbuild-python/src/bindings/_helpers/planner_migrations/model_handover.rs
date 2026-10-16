//! Adapt immutable migration fingerprints without changing their persisted representation.

use crate::bindings::_helpers::analysis::model_reads;
use crate::bindings::_helpers::compile_driver::python_calls::imported;
use crate::bindings::_helpers::planner_migrations::column_objects::{native, replace, text};
use crate::bindings::_helpers::planner_migrations::constants::MIGRATION_MODEL_NAME_METADATA_KEY;
use crate::bindings::_helpers::records::ids::NativeAttr;
use crate::bindings::_helpers::records::registry;
use crate::bindings::_helpers::state_rows::timestamps::presumed_utc;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods};

pub(super) fn applies(
    model: &Bound<'_, PyAny>,
    event: &Bound<'_, PyAny>,
    snapshot: &Bound<'_, PyAny>,
) -> PyResult<bool> {
    let own = snapshot
        .getattr("fingerprints")?
        .getattr("models")?
        .call_method1("get", (model_reads::name_object(model)?,))?;
    Ok(own.is_none()
        || presumed_utc(&own.getattr("ts")?)? < presumed_utc(&event.getattr("created_at")?)?)
}

pub(super) fn handover<'py>(
    model: &Bound<'py, PyAny>,
    fingerprint: &Bound<'py, PyAny>,
    version: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    if fingerprint.is_none() {
        return Ok(fingerprint.clone());
    }
    let py = model.py();
    let mut metadata = fingerprint.getattr("metadata_json")?;
    let json = py.import("json")?;
    let payload = match json.call_method1("loads", (&metadata,)) {
        Ok(payload) => payload,
        Err(error) if error.is_instance(py, &json.getattr("JSONDecodeError")?) => {
            py.None().into_bound(py)
        }
        Err(error) => return Err(error),
    };
    let key = MIGRATION_MODEL_NAME_METADATA_KEY;
    if let Ok(payload) = payload.cast::<PyDict>()
        && payload.contains(key)?
    {
        payload.set_item(key, model_reads::name_object(model)?)?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("sort_keys", true)?;
        kwargs.set_item("separators", (",", ":"))?;
        kwargs.set_item("default", imported(py, "builtins", "str")?)?;
        metadata = json.getattr("dumps")?.call((payload,), Some(&kwargs))?;
    }
    let destination = model_reads::destination(model)?;
    replace(
        fingerprint,
        &[
            ("node_name", model_reads::name_object(model)?),
            ("target_database", destination.getattr("database")?),
            ("target_schema", destination.getattr("schema")?),
            ("target_name", destination.getattr("name")?),
            (
                "version_hash",
                if version.is_truthy()? {
                    version.clone()
                } else {
                    fingerprint.getattr("version_hash")?
                },
            ),
            ("metadata_json", metadata),
        ],
    )
}

pub(super) fn equivalent<'py>(
    model: &Bound<'py, PyAny>,
    handover: Bound<'py, PyAny>,
    destinations: &Bound<'py, PyAny>,
    dialect: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = model.py();
    if handover.is_none()
        || !destinations.contains(
            registry::native(py, NativeAttr::StoredMigrationFingerprint)?.call1((&handover,))?,
        )?
    {
        return Ok(handover);
    }
    replace(
        &handover,
        &[
            ("definition", model_reads::query_sql(model)?),
            (
                "definition_hash",
                native(
                    py,
                    NativeAttr::ComputeQueryHash,
                    &[
                        ("query_sql", model_reads::query_sql(model)?),
                        ("dialect", dialect.clone()),
                    ],
                )?,
            ),
        ],
    )
}

pub(super) fn empty_version<'py>(
    model: &Bound<'py, PyAny>,
    fingerprint: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    handover(model, fingerprint, &text(model.py(), ""))
}
