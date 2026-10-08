//! Python audit and hook argument values read as plain argument values.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{
    PyBool, PyDict, PyDictMethods, PyFloat, PyInt, PyList, PyListMethods, PyString, PyTuple,
};
use sqlbuild_attachments::audits::models::ArgumentValue;

/// Read a `dict[str, object]` in insertion order, or None for values Python must judge.
pub(crate) fn argument_pairs(
    arguments: &Bound<'_, PyDict>,
) -> PyResult<Option<Vec<(String, ArgumentValue)>>> {
    let mut pairs: Vec<(String, ArgumentValue)> = Vec::with_capacity(arguments.len());
    for (key, value) in arguments.iter() {
        if !key.is_exact_instance_of::<PyString>() {
            return Ok(None);
        }
        let Some(argument) = argument_value(&value)? else {
            return Ok(None);
        };
        pairs.push((key.extract()?, argument));
    }
    Ok(Some(pairs))
}

/// One plain or opaque value; tuples, list subclasses and non-finite floats defer to Python.
fn argument_value(value: &Bound<'_, PyAny>) -> PyResult<Option<ArgumentValue>> {
    if value.is_none() {
        return Ok(Some(ArgumentValue::Null));
    }
    if value.is_instance_of::<PyBool>() {
        return Ok(Some(ArgumentValue::Boolean(value.extract()?)));
    }
    if value.is_instance_of::<PyInt>() {
        return Ok(Some(ArgumentValue::Number(value.str()?.extract()?)));
    }
    if value.is_instance_of::<PyFloat>() {
        let number: f64 = value.extract()?;
        if !number.is_finite() {
            return Ok(None);
        }
        return Ok(Some(ArgumentValue::Number(value.str()?.extract()?)));
    }
    if value.is_instance_of::<PyString>() {
        if let Ok(text) = value.extract::<String>() {
            return Ok(Some(ArgumentValue::Text(text)));
        }
        return Ok(None);
    }
    if value.is_instance_of::<PyTuple>() || value.is_instance_of::<PyList>() {
        if !value.is_exact_instance_of::<PyList>() {
            return Ok(None);
        }
    } else {
        return Ok(Some(ArgumentValue::Opaque));
    }
    let list: &Bound<'_, PyList> = value.downcast_exact::<PyList>()?;
    let mut items: Vec<ArgumentValue> = Vec::with_capacity(list.len());
    for item in list.iter() {
        let Some(argument) = argument_value(&item)? else {
            return Ok(None);
        };
        items.push(argument);
    }
    Ok(Some(ArgumentValue::List(items)))
}
