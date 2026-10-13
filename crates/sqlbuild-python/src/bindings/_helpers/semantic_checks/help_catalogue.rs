//! The semantic diagnostic help catalogue, for Python's tests and corpus tooling.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::semantic_checks::main::semantic_help_catalogue::semantic_help_catalogue as catalogue;

/// Each semantic diagnostic code and its help.
#[pyfunction]
fn semantic_help_catalogue() -> Vec<(&'static str, &'static str)> {
    catalogue().to_vec()
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(semantic_help_catalogue, module)?)
}
