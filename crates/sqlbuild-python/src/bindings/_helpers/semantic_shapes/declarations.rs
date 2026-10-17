//! The function names and declared types native binding treats as known.

use std::collections::BTreeSet;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyDict, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::records::fields::field as native_field;

const UNKNOWN: &str = "UNKNOWN";

/// Each declared function's name and its UDF and table-function analysis names, sorted.
pub(crate) fn function_names(functions: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    let mut names: BTreeSet<String> = BTreeSet::new();
    for function in functions.try_iter()? {
        let name: String = native_field(&function?, "name")?.extract()?;
        names.insert(format!("__sqlbuild_udf_{name}"));
        names.insert(format!("__sqlbuild_table_function_{name}"));
        names.insert(name);
    }
    Ok(names.into_iter().collect())
}

/// Types named by relation shapes and function signatures, sorted, `UNKNOWN` left out.
pub(crate) fn declared_types(
    functions: &Bound<'_, PyAny>,
    column_types: &Bound<'_, PyAny>,
) -> PyResult<Vec<String>> {
    let mut types: BTreeSet<String> = BTreeSet::new();
    for columns in column_types.call_method0("values")?.try_iter()? {
        for column_type in columns?.call_method0("values")?.try_iter()? {
            types.insert(column_type?.extract()?);
        }
    }
    for function in functions.try_iter()? {
        let function: Bound<'_, PyAny> = function?;
        for argument in native_field(&function, "arguments")?.try_iter()? {
            types.insert(native_field(&argument?, "type")?.extract()?);
        }
        let returns: Bound<'_, PyAny> = native_field(&function, "return_columns")?;
        for column in returns.try_iter()? {
            types.insert(native_field(&column?, "type")?.extract()?);
        }
        if !returns.is_truthy()? {
            types.insert(native_field(&function, "returns")?.extract()?);
        }
    }
    types.remove(UNKNOWN);
    Ok(types.into_iter().collect())
}

/// `known_function_names` as a sorted tuple.
#[pyfunction]
fn known_function_names<'py>(functions: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyTuple>> {
    PyTuple::new(functions.py(), function_names(functions)?)
}

/// `known_declared_types(*, functions, column_types)` as a sorted tuple.
#[pyfunction]
#[pyo3(signature = (**request))]
fn known_declared_types<'py>(
    request: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let request = Request::new("known_declared_types", request)?;
    let types: Vec<String> =
        declared_types(&request.get("functions")?, &request.get("column_types")?)?;
    PyTuple::new(request.py(), types)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(known_function_names, module)?)?;
    module.add_function(wrap_pyfunction!(known_declared_types, module)?)
}
