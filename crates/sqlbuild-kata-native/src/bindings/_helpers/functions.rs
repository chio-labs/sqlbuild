//! Register the versioned Python boundary for the native kata engine.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyErr, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::configuration::main::load;
use crate::constants::API_VERSION;
use crate::engine::main::evaluate;
use crate::models::CatalogueResponse;
use crate::rules::main::{catalogue, selected_codes};

const SKILL_OWNER: &str = "sqlbuild";
const SKILL_IDENTITY: &str = "sqlbuild-kata";

fn value_error(error: impl std::fmt::Display) -> PyErr {
    PyValueError::new_err(error.to_string())
}

#[pyfunction]
fn evaluate_json(request_json: &str) -> PyResult<String> {
    evaluate::evaluate_json(request_json).map_err(value_error)
}

#[pyfunction]
fn load_config_json(project_dir: &str) -> PyResult<String> {
    load::load_config_json(std::path::Path::new(project_dir)).map_err(value_error)
}

#[pyfunction]
fn catalogue_json() -> PyResult<String> {
    serde_json::to_string(&CatalogueResponse {
        version: API_VERSION,
        rules: catalogue::catalogue(),
    })
    .map_err(value_error)
}

#[pyfunction]
fn selected_codes_json(request_json: &str) -> PyResult<String> {
    selected_codes::selected_codes_json(request_json).map_err(value_error)
}

#[pyfunction]
fn render_owned_skill(content: &str, input_fingerprint: &str) -> PyResult<String> {
    fensu_policy::render_owned_skill(
        SKILL_OWNER,
        SKILL_IDENTITY,
        input_fingerprint,
        content.as_bytes(),
    )
    .map_err(value_error)
    .and_then(|value| String::from_utf8(value).map_err(value_error))
}

#[pyfunction]
fn skill_freshness(content: Option<&str>, input_fingerprint: &str) -> String {
    let freshness = fensu_policy::skill_freshness(
        content.map(str::as_bytes),
        SKILL_OWNER,
        SKILL_IDENTITY,
        input_fingerprint,
    );
    format!("{freshness:?}").to_lowercase()
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(evaluate_json, module)?)?;
    module.add_function(wrap_pyfunction!(load_config_json, module)?)?;
    module.add_function(wrap_pyfunction!(catalogue_json, module)?)?;
    module.add_function(wrap_pyfunction!(selected_codes_json, module)?)?;
    module.add_function(wrap_pyfunction!(render_owned_skill, module)?)?;
    module.add_function(wrap_pyfunction!(skill_freshness, module)?)?;
    module.add("API_VERSION", API_VERSION)?;
    Ok(())
}
