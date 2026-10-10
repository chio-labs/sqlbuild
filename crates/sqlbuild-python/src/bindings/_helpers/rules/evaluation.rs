//! Register the versioned Python boundary for the native Rules engine.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_rules::configuration::main::load;
use sqlbuild_rules::constants::API_VERSION;
use sqlbuild_rules::models::CatalogueResponse;
use sqlbuild_rules::rules::main::{catalogue, selected_codes};

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
fn load_config_json(project_dir: &str) -> PyResult<String> {
    compiler_guard(|| {
        load::load_config_json(std::path::Path::new(project_dir)).map_err(value_error)
    })
}

#[pyfunction]
fn catalogue_json() -> PyResult<String> {
    compiler_guard(|| {
        serde_json::to_string(&CatalogueResponse {
            version: API_VERSION,
            rules: catalogue::catalogue(),
        })
        .map_err(value_error)
    })
}

#[pyfunction]
fn selected_codes_json(request_json: &str) -> PyResult<String> {
    compiler_guard(|| selected_codes::selected_codes_json(request_json).map_err(value_error))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_custom_host_json, module)?)?;
    module.add_function(wrap_pyfunction!(load_config_json, module)?)?;
    module.add_function(wrap_pyfunction!(catalogue_json, module)?)?;
    module.add_function(wrap_pyfunction!(selected_codes_json, module)?)?;
    crate::bindings::_helpers::rules::rows::register(module)
}
