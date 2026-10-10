//! Register the versioned Python boundary for the native Rules engine.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyBytes, PyBytesMethods};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_rules::configuration::main::load;
use sqlbuild_rules::constants::API_VERSION;
use sqlbuild_rules::engine::main::{evaluate, evaluate_parsed, parse_parts};
use sqlbuild_rules::models::CatalogueResponse;
use sqlbuild_rules::rules::main::{catalogue, selected_codes};
use std::sync::Mutex;

use crate::bindings::_helpers::boundary::panics::{compiler_guard, value_error};
use crate::bindings::models::ParsedRulesRequest;
use crate::bindings::types::CompilerDetach;

#[pyfunction]
fn evaluate_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.compiler_detach(|| evaluate::evaluate_json(request_json))
        .map_err(value_error)
}

#[pyfunction]
fn parse_rules_parts(
    py: Python<'_>,
    request_json: Bound<'_, PyBytes>,
    model_jsons: Vec<Bound<'_, PyBytes>>,
    model_digests: Vec<String>,
) -> PyResult<ParsedRulesRequest> {
    let request: &[u8] = request_json.as_bytes();
    let models: Vec<&[u8]> = model_jsons.iter().map(|model| model.as_bytes()).collect();
    let parsed = py
        .compiler_detach(|| parse_parts::parse_parts(request, &models, &model_digests))
        .map_err(value_error)?;
    Ok(ParsedRulesRequest {
        request: Mutex::new(Some(parsed)),
    })
}

#[pyfunction]
fn evaluate_parsed_rules(
    py: Python<'_>,
    parsed: &Bound<'_, ParsedRulesRequest>,
) -> PyResult<String> {
    let request = parsed
        .borrow()
        .request
        .lock()
        .map_err(|_| value_error("rules request lock is poisoned"))?
        .take()
        .ok_or_else(|| value_error("rules request was already evaluated"))?;
    py.compiler_detach(|| evaluate_parsed::evaluate_parsed(request))
        .map_err(value_error)
}

#[pyfunction]
fn run_custom_host_json(py: Python<'_>, spec_json: &str) -> PyResult<String> {
    py.compiler_detach(|| {
        sqlbuild_rules::engine::main::custom_host::run_custom_host_json(spec_json)
    })
    .map_err(value_error)
}

#[pyfunction]
fn finalize_rule_findings_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.compiler_detach(|| {
        sqlbuild_rules::engine::main::finalize::finalize_findings_json(request_json)
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
    module.add_function(wrap_pyfunction!(evaluate_json, module)?)?;
    module.add_function(wrap_pyfunction!(parse_rules_parts, module)?)?;
    module.add_function(wrap_pyfunction!(evaluate_parsed_rules, module)?)?;
    module.add_function(wrap_pyfunction!(run_custom_host_json, module)?)?;
    module.add_function(wrap_pyfunction!(finalize_rule_findings_json, module)?)?;
    module.add_function(wrap_pyfunction!(load_config_json, module)?)?;
    module.add_function(wrap_pyfunction!(catalogue_json, module)?)?;
    module.add_function(wrap_pyfunction!(selected_codes_json, module)?)?;
    crate::bindings::_helpers::rules::rows::register(module)
}
