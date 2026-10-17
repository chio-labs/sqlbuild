//! Typed values read from raw authored configuration mappings, rejecting the wrong types.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyBool, PyInt, PyList, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::records::construct::error_class;
use crate::bindings::_helpers::records::fields::mapping_get;
use crate::bindings::_helpers::records::ids::ErrorId;

const DATETIME_MODULE: &str = "datetime";

/// `values.get(key)`, or `None` when the value is absent or `None`.
fn authored<'py>(values: &Bound<'py, PyAny>, key: &str) -> PyResult<Option<Bound<'py, PyAny>>> {
    let value: Bound<'py, PyAny> = mapping_get(values, key)?;
    Ok(Some(value).filter(|value| !value.is_none()))
}

/// `ConfigValueTypeError(key=key, expected=expected, actual_type=type(value))`.
fn wrong_type(key: &str, expected: &str, value: &Bound<'_, PyAny>) -> PyErr {
    match config_value_type_error(key, expected, &value.get_type().into_any()) {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}

/// The `ConfigValueTypeError` naming `key`, the `expected` kind and the value's `actual_type`.
pub(crate) fn config_value_type_error<'py>(
    key: &str,
    expected: &str,
    actual_type: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = actual_type.py();
    let type_name: String = actual_type.getattr("__name__")?.extract()?;
    call_with(
        &error_class(py, ErrorId::ConfigValueType)?,
        &[
            (
                "message",
                PyString::new(
                    py,
                    &format!("config key '{key}' expected {expected}, got {type_name}"),
                )
                .into_any(),
            ),
            ("key", PyString::new(py, key).into_any()),
            ("expected", PyString::new(py, expected).into_any()),
            ("actual_type", actual_type.clone()),
        ],
    )
}

/// An authored string, preserving a present empty string.
#[pyfunction(name = "get_config_str")]
#[pyo3(signature = (*, values, key))]
pub(crate) fn config_str<'py>(
    values: &Bound<'py, PyAny>,
    key: &str,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let Some(value) = authored(values, key)? else {
        return Ok(None);
    };
    if !value.is_instance_of::<PyString>() {
        return Err(wrong_type(key, "a string", &value));
    }
    Ok(Some(value))
}

/// An authored boolean, or `None` when the key is absent or `None`.
#[pyfunction(name = "get_config_bool")]
#[pyo3(signature = (*, values, key))]
pub(crate) fn config_bool<'py>(
    values: &Bound<'py, PyAny>,
    key: &str,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let Some(value) = authored(values, key)? else {
        return Ok(None);
    };
    if !value.is_instance_of::<PyBool>() {
        return Err(wrong_type(key, "a boolean", &value));
    }
    Ok(Some(value))
}

/// An authored sequence of strings as a tuple, or `None` when absent or `None`.
#[pyfunction(name = "get_config_string_tuple")]
#[pyo3(signature = (*, values, key))]
pub(crate) fn config_string_tuple<'py>(
    values: &Bound<'py, PyAny>,
    key: &str,
) -> PyResult<Option<Bound<'py, PyTuple>>> {
    let Some(value) = authored(values, key)? else {
        return Ok(None);
    };
    if !(value.is_instance_of::<PyList>() || value.is_instance_of::<PyTuple>()) {
        return Err(wrong_type(key, "a list or tuple of strings", &value));
    }
    let items: Vec<Bound<'py, PyAny>> = value.try_iter()?.collect::<PyResult<_>>()?;
    if !items.iter().all(|item| item.is_instance_of::<PyString>()) {
        return Err(wrong_type(key, "a list or tuple of strings", &value));
    }
    PyTuple::new(values.py(), items).map(Some)
}

/// An authored integer, excluding booleans, or `None` when absent or `None`.
#[pyfunction(name = "get_config_int")]
#[pyo3(signature = (*, values, key))]
pub(crate) fn config_int<'py>(
    values: &Bound<'py, PyAny>,
    key: &str,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let Some(value) = authored(values, key)? else {
        return Ok(None);
    };
    if value.is_instance_of::<PyBool>() || !value.is_instance_of::<PyInt>() {
        return Err(wrong_type(key, "an integer", &value));
    }
    Ok(Some(value))
}

/// A cursor bound as text from a string, integer, date or datetime.
#[pyfunction(name = "get_config_cursor_bound")]
#[pyo3(signature = (*, values, key))]
pub(crate) fn config_cursor_bound<'py>(
    values: &Bound<'py, PyAny>,
    key: &str,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let Some(value) = authored(values, key)? else {
        return Ok(None);
    };
    let py = values.py();
    let date: Bound<'py, PyAny> = imported(py, DATETIME_MODULE, "date")?;
    let datetime: Bound<'py, PyAny> = imported(py, DATETIME_MODULE, "datetime")?;
    let dated: bool = value.is_instance(&date)? || value.is_instance(&datetime)?;
    if value.is_instance_of::<PyBool>()
        || !(dated || value.is_instance_of::<PyString>() || value.is_instance_of::<PyInt>())
    {
        return Err(wrong_type(
            key,
            "a string, integer, date, or datetime",
            &value,
        ));
    }
    if dated {
        return value.call_method0("isoformat").map(Some);
    }
    value.str().map(|text| Some(text.into_any()))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(config_str, module)?)?;
    module.add_function(wrap_pyfunction!(config_bool, module)?)?;
    module.add_function(wrap_pyfunction!(config_string_tuple, module)?)?;
    module.add_function(wrap_pyfunction!(config_int, module)?)?;
    module.add_function(wrap_pyfunction!(config_cursor_bound, module)?)?;
    Ok(())
}
