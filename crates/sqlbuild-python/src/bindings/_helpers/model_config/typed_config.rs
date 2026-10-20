//! Model config values read as typed config nodes, kept on the config record once converted.

use std::sync::Arc;

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::pyclass;
use pyo3::types::PyDict;
use sqlbuild_model_config::config_values::errors::ConfigTypeError;
use sqlbuild_model_config::config_values::main::checked_text::checked_text;
use sqlbuild_model_config::config_values::main::config_entry::config_entry;
use sqlbuild_model_config::config_values::models::ConfigNode;

use crate::bindings::_helpers::model_config::config_nodes::{
    HostHandle, PyConfigEntries, PyConfigNode, config_entries, config_node, config_object,
};
use crate::bindings::_helpers::model_config::config_values::config_value_type_error;
use crate::bindings::_helpers::records::fields::{
    cached_value, field as native_field, store_cached,
};
use crate::bindings::_helpers::records::models::NativeRecord;

const CONFIG_FIELD: &str = "config";
const VALUES_FIELD: &str = "values";
/// The config record's cache slot holding its typed values; no Python attribute reads it.
const TYPED_VALUES_SLOT: &str = "__typed_values__";

/// A config record's values as typed config nodes.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct TypedConfigValues {
    entries: Arc<PyConfigEntries>,
}

/// The entries of a values mapping: a `dict` read directly, any other mapping through `items()`.
fn mapping_entries(values: &Bound<'_, PyAny>) -> PyResult<PyConfigEntries> {
    if let Ok(mapping) = values.cast::<PyDict>() {
        return config_entries(mapping);
    }
    values
        .call_method0("items")?
        .try_iter()?
        .map(|item| {
            let (key, value): (Bound<'_, PyAny>, Bound<'_, PyAny>) = item?.extract()?;
            Ok((config_node(&key)?, config_node(&value)?))
        })
        .collect()
}

/// Keep `entries` as the typed values of the config record `config`.
pub(crate) fn keep_typed_values(
    config: &Bound<'_, PyAny>,
    entries: Arc<PyConfigEntries>,
) -> PyResult<()> {
    let Ok(record) = config.cast::<NativeRecord>() else {
        return Ok(());
    };
    let typed: Py<TypedConfigValues> = Py::new(config.py(), TypedConfigValues { entries })?;
    store_cached(record, TYPED_VALUES_SLOT, &typed.into_any())
}

/// A config record's values as typed nodes, converted from its `values` once and kept.
pub(crate) fn typed_values(config: &Bound<'_, PyAny>) -> PyResult<Arc<PyConfigEntries>> {
    let py: Python<'_> = config.py();
    let Ok(record) = config.cast::<NativeRecord>() else {
        return Ok(Arc::new(mapping_entries(&native_field(
            config,
            VALUES_FIELD,
        )?)?));
    };
    if let Some(typed) = cached_value(record, TYPED_VALUES_SLOT)? {
        let typed: Bound<'_, TypedConfigValues> = typed.into_bound(py).cast_into()?;
        return Ok(Arc::clone(&typed.get().entries));
    }
    let entries: Arc<PyConfigEntries> =
        Arc::new(mapping_entries(&native_field(config, VALUES_FIELD)?)?);
    keep_typed_values(config, Arc::clone(&entries))?;
    Ok(entries)
}

/// A model's config values as typed nodes.
pub(crate) fn model_values(model: &Bound<'_, PyAny>) -> PyResult<Arc<PyConfigEntries>> {
    typed_values(&native_field(model, CONFIG_FIELD)?)
}

/// The `ConfigValueTypeError` a typed read raises, naming the value's Python type.
pub(crate) fn type_error(py: Python<'_>, error: &ConfigTypeError<'_, HostHandle>) -> PyErr {
    let raised = || -> PyResult<PyErr> {
        let actual_type = config_object(py, error.value)?.get_type().into_any();
        Ok(PyErr::from_value(config_value_type_error(
            &error.key,
            error.expected,
            &actual_type,
        )?))
    };
    raised().unwrap_or_else(|error| error)
}

/// The exact text of a string node; a string Python cannot encode raises as reading it does.
pub(crate) fn node_text(py: Python<'_>, node: &PyConfigNode) -> PyResult<String> {
    match node {
        ConfigNode::Str(text) => Ok(text.clone()),
        ConfigNode::Host(host) if host.facts.strict_text => {
            Ok(host.facts.text.clone().unwrap_or_default())
        }
        _ => config_object(py, node)?.extract(),
    }
}

/// `key`'s string value, or `None` when absent or `None`.
pub(crate) fn config_text(
    py: Python<'_>,
    entries: &[(PyConfigNode, PyConfigNode)],
    key: &str,
) -> PyResult<Option<String>> {
    checked_text(key, config_entry(entries, key))
        .map_err(|error| type_error(py, &error))?
        .map(|value| node_text(py, value))
        .transpose()
}

/// `key`'s string value as its Python object, or `None` when absent or `None`.
pub(crate) fn config_text_object<'py>(
    py: Python<'py>,
    entries: &[(PyConfigNode, PyConfigNode)],
    key: &str,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    checked_text(key, config_entry(entries, key))
        .map_err(|error| type_error(py, &error))?
        .map(|value| config_object(py, value))
        .transpose()
}
