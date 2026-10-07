//! Authored header values as the Python objects the model header parser builds.

use pyo3::prelude::{IntoPyObject, Py, PyAny, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyList, PyTuple};

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
        AuthoredValue::BareWord(value) => {
            marker_to_python(py, "word", value.into_pyobject(py)?.unbind().into_any())
        }
        AuthoredValue::String(value) => Ok(value.into_pyobject(py)?.unbind().into_any()),
        AuthoredValue::List(values) => {
            let projected = values
                .into_iter()
                .map(|item| authored_value_to_python(py, item))
                .collect::<PyResult<Vec<_>>>()?;
            Ok(PyList::new(py, projected)?.unbind().into_any())
        }
        AuthoredValue::Map(values) => map_to_python(py, values),
        AuthoredValue::Set(values) => marker_to_python(
            py,
            "set",
            authored_value_to_python(py, AuthoredValue::List(values))?,
        ),
        AuthoredValue::Tuple(values) => marker_to_python(
            py,
            "tuple",
            authored_value_to_python(py, AuthoredValue::List(values))?,
        ),
        AuthoredValue::TypedConstant(values) => {
            marker_to_python(py, "constant", map_to_python(py, values)?)
        }
        AuthoredValue::InlineSqlHook(statement) => marker_to_python(
            py,
            "inline_sql",
            statement.into_pyobject(py)?.unbind().into_any(),
        ),
        AuthoredValue::NamedSqlHook(name, kwargs) => hook_marker(py, "sql", name, kwargs),
        AuthoredValue::PythonHook(name, kwargs) => hook_marker(py, "python", name, kwargs),
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

fn marker_to_python(py: Python<'_>, kind: &str, value: Py<PyAny>) -> PyResult<Py<PyAny>> {
    Ok(
        PyTuple::new(py, [kind.into_pyobject(py)?.unbind().into_any(), value])?
            .unbind()
            .into_any(),
    )
}

fn hook_marker(
    py: Python<'_>,
    kind: &str,
    name: String,
    kwargs: Vec<(String, sqlbuild_sqltext::compiler::models::AuthoredValue)>,
) -> PyResult<Py<PyAny>> {
    let payload = PyTuple::new(
        py,
        [
            name.into_pyobject(py)?.unbind().into_any(),
            map_to_python(py, kwargs)?,
        ],
    )?;
    marker_to_python(py, kind, payload.unbind().into_any())
}

pub(crate) fn optional_authored_value_to_python(
    py: Python<'_>,
    value: Option<sqlbuild_sqltext::compiler::models::AuthoredValue>,
) -> PyResult<Option<Py<PyAny>>> {
    value
        .map(|item| authored_value_to_python(py, item))
        .transpose()
}
