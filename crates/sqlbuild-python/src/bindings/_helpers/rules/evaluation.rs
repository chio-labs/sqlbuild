//! Register the versioned Python boundary for the native Rules engine.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_rules::rules::main::selected_codes;

use crate::bindings::_helpers::boundary::panics::{compiler_guard, value_error};
use crate::bindings::types::CompilerDetach;

#[pyfunction]
fn run_custom_host_json(py: Python<'_>, spec_json: &str) -> PyResult<String> {
    py.compiler_detach(|| {
        sqlbuild_rules::engine::main::custom_host::run_custom_host_json(spec_json)
    })
    .map_err(value_error)
}

#[pyfunction]
fn selected_codes_json(request_json: &str) -> PyResult<String> {
    compiler_guard(|| selected_codes::selected_codes_json(request_json).map_err(value_error))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_custom_host_json, module)?)?;
    module.add_function(wrap_pyfunction!(selected_codes_json, module)?)?;
    crate::bindings::_helpers::rules::rows::register(module)
}
