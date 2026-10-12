//! Wildcard name matching for the discovery directory snapshot.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyString, PyStringMethods};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::text::main::glob_name_match::glob_name_match as name_matches;

/// Whether a directory entry name matches a single-name glob `pattern`.
#[pyfunction]
fn glob_name_match(name: &Bound<'_, PyString>, pattern: &str, ignore_case: bool) -> bool {
    name_matches(&name.to_string_lossy(), pattern, ignore_case)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(glob_name_match, module)?)
}
