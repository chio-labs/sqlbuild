//! Emit a command's JSON report as `orjson.dumps(report, option=OPT_INDENT_2)` would.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{
    PyBool, PyBoolMethods, PyDict, PyDictMethods, PyFloat, PyInt, PyList, PyString,
    PyStringMethods, PyTuple,
};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonInteger, JsonValue, OrjsonOptions};

use crate::bindings::_helpers::boundary::panics::compiler_guard;

/// The report text, or `None` when it holds a value orjson would not encode the same way.
#[pyfunction]
fn emit_json_report(report: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    compiler_guard(|| {
        let Some(value) = json_value(report)? else {
            return Ok(None);
        };
        let dialect = JsonDialect::Orjson(OrjsonOptions {
            indent_2: true,
            sort_keys: false,
        });
        if let Ok(text) = dumps(&value, &dialect) {
            return Ok(Some(text));
        }
        Ok(None)
    })
}

fn json_value(value: &Bound<'_, PyAny>) -> PyResult<Option<JsonValue>> {
    if value.is_none() {
        return Ok(Some(JsonValue::Null));
    }
    if let Ok(flag) = value.downcast::<PyBool>() {
        return Ok(Some(JsonValue::Bool(flag.is_true())));
    }
    if value.is_instance_of::<PyInt>() {
        return Ok(integer(value));
    }
    if value.is_instance_of::<PyFloat>() {
        return Ok(Some(JsonValue::Float(value.extract::<f64>()?)));
    }
    if let Ok(text) = value.downcast::<PyString>() {
        return Ok(match text.to_str() {
            Ok(text) => Some(JsonValue::String(text.to_owned())),
            Err(_) => None,
        });
    }
    if value.is_instance_of::<PyList>() || value.is_instance_of::<PyTuple>() {
        return array(value);
    }
    if let Ok(mapping) = value.downcast::<PyDict>() {
        return object(mapping);
    }
    Ok(None)
}

/// A 64-bit integer; orjson rejects wider integers, so those defer to Python.
fn integer(value: &Bound<'_, PyAny>) -> Option<JsonValue> {
    if let Ok(signed) = value.extract::<i64>() {
        return Some(JsonValue::Integer(JsonInteger::from(signed)));
    }
    match value.extract::<u64>() {
        Ok(unsigned) => Some(JsonValue::Integer(JsonInteger::from(unsigned))),
        Err(_) => None,
    }
}

fn array(value: &Bound<'_, PyAny>) -> PyResult<Option<JsonValue>> {
    let mut items: Vec<JsonValue> = Vec::new();
    for item in value.try_iter()? {
        match json_value(&item?)? {
            Some(item) => items.push(item),
            None => return Ok(None),
        }
    }
    Ok(Some(JsonValue::Array(items)))
}

fn object(mapping: &Bound<'_, PyDict>) -> PyResult<Option<JsonValue>> {
    let mut entries: Vec<(String, JsonValue)> = Vec::with_capacity(mapping.len());
    for (key, item) in mapping.iter() {
        let Ok(key) = key.downcast::<PyString>() else {
            return Ok(None);
        };
        let Ok(key) = key.to_str() else {
            return Ok(None);
        };
        match json_value(&item)? {
            Some(item) => entries.push((key.to_owned(), item)),
            None => return Ok(None),
        }
    }
    Ok(Some(JsonValue::Object(entries)))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(emit_json_report, module)?)
}
