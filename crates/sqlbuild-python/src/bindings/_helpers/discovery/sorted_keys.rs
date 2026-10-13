//! Header key sets as the sorted lists native discovery options take.

use pyo3::prelude::{Bound, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyFrozenSet, PyFrozenSetMethods};

use crate::bindings::_helpers::compile_driver::python_calls::imported;

const CONSTANTS_MODULE: &str = "sqlbuild.compiler.discovery.constants";

/// `sorted(constants.<name>)`: a header key set, sorted by code point as Python sorts it.
pub(crate) fn sorted_keys(py: Python<'_>, name: &str) -> PyResult<Vec<String>> {
    let keys: Bound<'_, PyFrozenSet> = imported(py, CONSTANTS_MODULE, name)?.downcast_into()?;
    let mut keys: Vec<String> = keys
        .iter()
        .map(|key| key.extract())
        .collect::<PyResult<_>>()?;
    keys.sort();
    Ok(keys)
}
