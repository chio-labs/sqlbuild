//! `Path.glob` name matching for the discovery directory snapshot.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::text::main::python_glob_name_match::python_glob_name_match;

/// Whether a directory entry name matches a single-name glob `pattern`.
#[pyfunction]
fn glob_name_match(name: &str, pattern: &str, ignore_case: bool) -> bool {
    python_glob_name_match(name, pattern, ignore_case)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(glob_name_match, module)?)
}
