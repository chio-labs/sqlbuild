//! Render and check the generated rules skill.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::boundary::panics::compiler_guard;
use crate::bindings::_helpers::rules::selection::rules_error;

const SKILL_OWNER: &str = "sqlbuild";
const SKILL_IDENTITY: &str = "sqlbuild-rules";

/// Generated guidance with its ownership header; a policy failure raises `RulesError`.
#[pyfunction]
#[pyo3(signature = (*, content, input_fingerprint))]
fn render_owned_skill(py: Python<'_>, content: &str, input_fingerprint: &str) -> PyResult<String> {
    let rendered: Result<String, String> = compiler_guard(|| {
        Ok(fensu_policy::render_owned_skill(
            SKILL_OWNER,
            SKILL_IDENTITY,
            input_fingerprint,
            content.as_bytes(),
        )
        .map_err(|error| error.to_string())
        .and_then(|value| String::from_utf8(value).map_err(|error| error.to_string())))
    })?;
    rendered.map_err(|message| rules_error(py, &message, None))
}

/// Whether generated guidance is current, stale or foreign under the ownership contract.
#[pyfunction]
#[pyo3(signature = (*, content, input_fingerprint))]
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
    module.add_function(wrap_pyfunction!(render_owned_skill, module)?)?;
    module.add_function(wrap_pyfunction!(skill_freshness, module)?)?;
    Ok(())
}
