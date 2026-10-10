//! Emit a command's JSON report as orjson would, or as `json.dumps` does when orjson rejects it.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{
    PyBool, PyBoolMethods, PyDict, PyDictMethods, PyFloat, PyInt, PyList, PyString,
    PyStringMethods, PyTuple,
};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{
    JsonDialect, JsonInteger, JsonValue, OrjsonOptions, StdlibJsonOptions,
};

use crate::bindings::_helpers::boundary::panics::compiler_guard;

/// What converting the report found besides its values.
#[derive(Default)]
struct Conversion {
    /// orjson would raise `TypeError` (an integer beyond 64 bits or a non-string key).
    orjson_rejects: bool,
}

/// The report text, or `None` when it holds a value neither encoder path is reproduced for.
#[pyfunction]
fn emit_json_report(report: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    compiler_guard(|| {
        let mut conversion: Conversion = Conversion::default();
        let Some(value) = conversion.json_value(report)? else {
            return Ok(None);
        };
        let dialect: JsonDialect = if conversion.orjson_rejects {
            JsonDialect::Stdlib(StdlibJsonOptions::new(Some(2)))
        } else {
            JsonDialect::Orjson(OrjsonOptions {
                indent_2: true,
                sort_keys: false,
            })
        };
        if let Ok(text) = dumps(&value, &dialect) {
            return Ok(Some(text));
        }
        Ok(None)
    })
}

impl Conversion {
    fn json_value(&mut self, value: &Bound<'_, PyAny>) -> PyResult<Option<JsonValue>> {
        if value.is_none() {
            return Ok(Some(JsonValue::Null));
        }
        if let Ok(flag) = value.downcast::<PyBool>() {
            return Ok(Some(JsonValue::Bool(flag.is_true())));
        }
        if value.is_instance_of::<PyInt>() {
            return self.integer(value);
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
            return self.array(value);
        }
        if let Ok(mapping) = value.downcast::<PyDict>() {
            return self.object(mapping);
        }
        Ok(None)
    }

    /// orjson encodes 64-bit integers; wider ones make it raise, so `json.dumps` writes them.
    fn integer(&mut self, value: &Bound<'_, PyAny>) -> PyResult<Option<JsonValue>> {
        if let Ok(signed) = value.extract::<i64>() {
            return Ok(Some(JsonValue::Integer(JsonInteger::from(signed))));
        }
        if let Ok(unsigned) = value.extract::<u64>() {
            return Ok(Some(JsonValue::Integer(JsonInteger::from(unsigned))));
        }
        self.orjson_rejects = true;
        let decimal: String = value.str()?.to_str()?.to_owned();
        Ok(JsonInteger::parse(&decimal).map(JsonValue::Integer))
    }

    fn array(&mut self, value: &Bound<'_, PyAny>) -> PyResult<Option<JsonValue>> {
        let mut items: Vec<JsonValue> = Vec::new();
        for item in value.try_iter()? {
            match self.json_value(&item?)? {
                Some(item) => items.push(item),
                None => return Ok(None),
            }
        }
        Ok(Some(JsonValue::Array(items)))
    }

    fn object(&mut self, mapping: &Bound<'_, PyDict>) -> PyResult<Option<JsonValue>> {
        let mut entries: Vec<(String, JsonValue)> = Vec::with_capacity(mapping.len());
        for (key, item) in mapping.iter() {
            let Some(key) = self.object_key(&key)? else {
                return Ok(None);
            };
            match self.json_value(&item)? {
                Some(item) => entries.push((key, item)),
                None => return Ok(None),
            }
        }
        Ok(Some(JsonValue::Object(entries)))
    }

    /// A string key, or the text `json.dumps` writes for a scalar key orjson would reject.
    fn object_key(&mut self, key: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
        if let Ok(text) = key.downcast::<PyString>() {
            return Ok(match text.to_str() {
                Ok(text) => Some(text.to_owned()),
                Err(_) => None,
            });
        }
        self.orjson_rejects = true;
        if key.is_none() {
            return Ok(Some("null".to_owned()));
        }
        if let Ok(flag) = key.downcast::<PyBool>() {
            return Ok(Some(
                if flag.is_true() { "true" } else { "false" }.to_owned(),
            ));
        }
        if key.is_instance_of::<PyInt>() {
            return Ok(Some(key.str()?.to_str()?.to_owned()));
        }
        Ok(None)
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(emit_json_report, module)?)
}
