//! Python audit argument values read as plain argument values.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{
    PyBool, PyDict, PyDictMethods, PyFloat, PyInt, PyList, PyListMethods, PyString,
    PyStringMethods, PyTuple, PyTupleMethods,
};
use sqlbuild_attachments::audits::models::ArgumentValue;

/// Read a `dict[str, object]` in insertion order, leaving out keys no parameter can name.
pub(crate) fn argument_pairs(
    arguments: &Bound<'_, PyDict>,
) -> PyResult<Vec<(String, ArgumentValue)>> {
    let mut pairs: Vec<(String, ArgumentValue)> = Vec::with_capacity(arguments.len());
    for (key, value) in arguments.iter() {
        if let Ok(key) = key.downcast::<PyString>() {
            pairs.push((key.to_string_lossy().into_owned(), argument_value(&value)?));
        }
    }
    Ok(pairs)
}

/// One plain value; text with lone surrogates, rejected where it enters a compile, reads lossily.
fn argument_value(value: &Bound<'_, PyAny>) -> PyResult<ArgumentValue> {
    if value.is_none() {
        return Ok(ArgumentValue::Null);
    }
    if value.is_instance_of::<PyBool>() {
        return Ok(ArgumentValue::Boolean(value.extract()?));
    }
    if value.is_instance_of::<PyInt>() || value.is_instance_of::<PyFloat>() {
        return Ok(ArgumentValue::Number(
            value.str()?.to_string_lossy().into_owned(),
        ));
    }
    if let Ok(text) = value.downcast::<PyString>() {
        return Ok(ArgumentValue::Text(text.to_string_lossy().into_owned()));
    }
    if let Ok(items) = value.downcast::<PyList>() {
        return Ok(ArgumentValue::List(
            items
                .iter()
                .map(|item| argument_value(&item))
                .collect::<PyResult<_>>()?,
        ));
    }
    if let Ok(items) = value.downcast::<PyTuple>() {
        return Ok(ArgumentValue::Tuple(
            items
                .iter()
                .map(|item| argument_value(&item))
                .collect::<PyResult<_>>()?,
        ));
    }
    Ok(ArgumentValue::Opaque)
}
