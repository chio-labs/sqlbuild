//! Authored header values as the Python header objects: scalars, sets, constants and hooks.

use pyo3::prelude::{IntoPyObject, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyList, PyTuple};
use sqlbuild_sqltext::compiler::main::header_word_value::header_word_value;
use sqlbuild_sqltext::compiler::models::HeaderWord;

const SQL_VALUES_MODULE: &str = "sqlbuild.sql_values.models";
const DISCOVERY_MODELS_MODULE: &str = "sqlbuild.compiler.discovery.models";

fn word_to_python(py: Python<'_>, word: String) -> PyResult<Py<PyAny>> {
    match header_word_value(&word) {
        HeaderWord::Bool(value) => Ok(value.into_pyobject(py)?.to_owned().unbind().into_any()),
        HeaderWord::Null => Ok(py.None()),
        HeaderWord::Integer(digits) => match digits.parse::<i64>() {
            Ok(value) => Ok(value.into_pyobject(py)?.unbind().into_any()),
            Err(_) => Ok(py
                .import("builtins")?
                .getattr("int")?
                .call1((digits,))?
                .unbind()),
        },
        HeaderWord::Float(value) => Ok(value.into_pyobject(py)?.unbind().into_any()),
        HeaderWord::Text => Ok(word.into_pyobject(py)?.unbind().into_any()),
    }
}

fn instance(
    py: Python<'_>,
    (module, class): (&str, &str),
    arguments: &pyo3::Bound<'_, PyDict>,
) -> PyResult<Py<PyAny>> {
    Ok(py
        .import(module)?
        .getattr(class)?
        .call((), Some(arguments))?
        .unbind())
}

fn values_tuple(
    py: Python<'_>,
    values: Vec<sqlbuild_sqltext::compiler::models::AuthoredValue>,
) -> PyResult<Py<PyAny>> {
    let projected = values
        .into_iter()
        .map(|item| authored_value_to_python(py, item))
        .collect::<PyResult<Vec<_>>>()?;
    Ok(PyTuple::new(py, projected)?.unbind().into_any())
}

fn constant_call(
    py: Python<'_>,
    values: Vec<(String, sqlbuild_sqltext::compiler::models::AuthoredValue)>,
) -> PyResult<Py<PyAny>> {
    let arguments = values
        .into_iter()
        .map(|(key, value)| {
            let value = authored_value_to_python(py, value)?;
            PyTuple::new(py, [key.into_pyobject(py)?.unbind().into_any(), value])
        })
        .collect::<PyResult<Vec<_>>>()?;
    let keywords = PyDict::new(py);
    keywords.set_item("arguments", PyTuple::new(py, arguments)?)?;
    instance(py, (SQL_VALUES_MODULE, "AuthoredSqlValueCall"), &keywords)
}

fn authored_value_to_python(
    py: Python<'_>,
    value: sqlbuild_sqltext::compiler::models::AuthoredValue,
) -> PyResult<Py<PyAny>> {
    use sqlbuild_sqltext::compiler::models::AuthoredValue;

    match value {
        AuthoredValue::Null => Ok(py.None()),
        AuthoredValue::Boolean(value) => {
            Ok(value.into_pyobject(py)?.to_owned().unbind().into_any())
        }
        AuthoredValue::BareWord(value) => word_to_python(py, value),
        AuthoredValue::String(value) => Ok(value.into_pyobject(py)?.unbind().into_any()),
        AuthoredValue::List(values) => {
            let projected = values
                .into_iter()
                .map(|item| authored_value_to_python(py, item))
                .collect::<PyResult<Vec<_>>>()?;
            Ok(PyList::new(py, projected)?.unbind().into_any())
        }
        AuthoredValue::Map(values) => map_to_python(py, values),
        AuthoredValue::Set(values) => {
            let keywords = PyDict::new(py);
            keywords.set_item("values", values_tuple(py, values)?)?;
            instance(py, (SQL_VALUES_MODULE, "AuthoredSqlSet"), &keywords)
        }
        AuthoredValue::Tuple(values) => values_tuple(py, values),
        AuthoredValue::TypedConstant(values) => constant_call(py, values),
        AuthoredValue::InlineSqlHook(statement) => {
            let keywords = PyDict::new(py);
            keywords.set_item("statement", statement)?;
            instance(py, (DISCOVERY_MODELS_MODULE, "SqlHookEntry"), &keywords)
        }
        AuthoredValue::NamedSqlHook(name, kwargs) => hook(py, "NamedSqlHookEntry", name, kwargs),
        AuthoredValue::PythonHook(name, kwargs) => hook(py, "PythonHookEntry", name, kwargs),
    }
}

pub(crate) fn map_to_python(
    py: Python<'_>,
    values: Vec<(String, sqlbuild_sqltext::compiler::models::AuthoredValue)>,
) -> PyResult<Py<PyAny>> {
    let result = PyDict::new(py);
    for (key, value) in values {
        result.set_item(key, authored_value_to_python(py, value)?)?;
    }
    Ok(result.unbind().into_any())
}

fn hook(
    py: Python<'_>,
    class: &str,
    name: String,
    kwargs: Vec<(String, sqlbuild_sqltext::compiler::models::AuthoredValue)>,
) -> PyResult<Py<PyAny>> {
    let keywords = PyDict::new(py);
    keywords.set_item("name", name)?;
    keywords.set_item("kwargs", map_to_python(py, kwargs)?)?;
    instance(py, (DISCOVERY_MODELS_MODULE, class), &keywords)
}

pub(crate) fn optional_authored_value_to_python(
    py: Python<'_>,
    value: Option<sqlbuild_sqltext::compiler::models::AuthoredValue>,
) -> PyResult<Option<Py<PyAny>>> {
    value
        .map(|item| authored_value_to_python(py, item))
        .transpose()
}
