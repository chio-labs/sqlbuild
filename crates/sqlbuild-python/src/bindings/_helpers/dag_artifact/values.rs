//! Python values as `dataclasses.asdict` copies them and `json.dumps` would encode them.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{
    PyBool, PyBoolMethods, PyBytes, PyBytesMethods, PyDict, PyDictMethods, PyFloat, PyInt, PyList,
    PyString, PyStringMethods, PyTuple, PyTypeMethods,
};
use sqlbuild_analysis::dag_artifact::models::DagValue;
use sqlbuild_analysis::dag_artifact::types::DagKey;
use sqlbuild_core::json::models::JsonInteger;

use crate::bindings::_helpers::boundary::panics::NativeCompilerError;
use crate::bindings::_helpers::compile_outputs::json_report::float_key;

const DATACLASS_FIELDS: &str = "__dataclass_fields__";
const SURROGATE_KEY: &str = "a DAG artifact mapping key holds a lone surrogate, which the native \
                             encoder does not write";
const DATACLASSES_MODULE: &str = "dataclasses";

fn type_name(value: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(value.get_type().name()?.to_string())
}

/// A `str`, as UTF-16 code units when it holds lone surrogates.
pub(crate) fn text_value(text: &Bound<'_, PyString>) -> PyResult<DagValue> {
    if let Ok(text) = text.to_str() {
        return Ok(DagValue::String(text.to_owned()));
    }
    let encoded: Bound<'_, PyBytes> = text
        .call_method1("encode", ("utf-16-le", "surrogatepass"))?
        .downcast_into::<PyBytes>()?;
    Ok(DagValue::Utf16(
        encoded
            .as_bytes()
            .as_chunks::<2>()
            .0
            .iter()
            .map(|pair| u16::from_le_bytes([pair[0], pair[1]]))
            .collect(),
    ))
}

fn integer_value(value: &Bound<'_, PyAny>) -> PyResult<DagValue> {
    if let Ok(signed) = value.extract::<i64>() {
        return Ok(DagValue::Integer(JsonInteger::from(signed)));
    }
    if let Ok(unsigned) = value.extract::<u64>() {
        return Ok(DagValue::Integer(JsonInteger::from(unsigned)));
    }
    let decimal: String = value.str()?.to_str()?.to_owned();
    Ok(JsonInteger::parse(&decimal).map_or(DagValue::Null, DagValue::Integer))
}

/// A mapping key as `json.dumps` writes it, or its `TypeError` message.
fn key_value(key: &Bound<'_, PyAny>) -> PyResult<DagKey> {
    if let Ok(text) = key.downcast::<PyString>() {
        return text
            .to_str()
            .map(|text| Ok(text.to_owned()))
            .map_err(|_| NativeCompilerError::new_err(SURROGATE_KEY));
    }
    if key.is_none() {
        return Ok(Ok("null".to_owned()));
    }
    if let Ok(flag) = key.downcast::<PyBool>() {
        return Ok(Ok(if flag.is_true() { "true" } else { "false" }.to_owned()));
    }
    if key.is_instance_of::<PyInt>() {
        return Ok(Ok(key.str()?.to_str()?.to_owned()));
    }
    if key.is_instance_of::<PyFloat>() {
        return float_key(key).map(Ok);
    }
    Ok(Err(format!(
        "keys must be str, int, float, bool or None, not {}",
        type_name(key)?
    )))
}

fn dataclass_value(value: &Bound<'_, PyAny>) -> PyResult<DagValue> {
    let fields: Bound<'_, PyAny> = value
        .py()
        .import(DATACLASSES_MODULE)?
        .getattr("fields")?
        .call1((value,))?;
    let mut entries: Vec<(DagKey, DagValue)> = Vec::new();
    for field in fields.try_iter()? {
        let name: Bound<'_, PyAny> = field?.getattr("name")?;
        let item: Bound<'_, PyAny> = value.getattr(name.downcast::<PyString>()?)?;
        entries.push((key_value(&name)?, dag_value(&item)?));
    }
    Ok(DagValue::Object(entries))
}

/// The value `asdict` copies into the artifact; refused leaves keep `json.dumps`'s message.
pub(crate) fn dag_value(value: &Bound<'_, PyAny>) -> PyResult<DagValue> {
    if value.is_none() {
        return Ok(DagValue::Null);
    }
    if value.get_type().hasattr(DATACLASS_FIELDS)? {
        return dataclass_value(value);
    }
    if value.is_instance_of::<PyList>() || value.is_instance_of::<PyTuple>() {
        return Ok(DagValue::Array(
            value
                .try_iter()?
                .map(|item| dag_value(&item?))
                .collect::<PyResult<_>>()?,
        ));
    }
    if let Ok(mapping) = value.downcast::<PyDict>() {
        return Ok(DagValue::Object(
            mapping
                .iter()
                .map(|(key, item)| Ok((key_value(&key)?, dag_value(&item)?)))
                .collect::<PyResult<_>>()?,
        ));
    }
    if let Ok(flag) = value.downcast::<PyBool>() {
        return Ok(DagValue::Bool(flag.is_true()));
    }
    if value.is_instance_of::<PyInt>() {
        return integer_value(value);
    }
    if value.is_instance_of::<PyFloat>() {
        return Ok(DagValue::Float(value.extract::<f64>()?));
    }
    if let Ok(text) = value.downcast::<PyString>() {
        return text_value(text);
    }
    Ok(DagValue::Unencodable(format!(
        "Object of type {} is not JSON serializable",
        type_name(value)?
    )))
}
