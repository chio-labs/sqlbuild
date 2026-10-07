//! Render and check the generated rules skill.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::boundary::panics::{compiler_guard, value_error};

const SKILL_OWNER: &str = "sqlbuild";
const SKILL_IDENTITY: &str = "sqlbuild-rules";

#[pyfunction]
fn render_owned_skill(content: &str, input_fingerprint: &str) -> PyResult<String> {
    compiler_guard(|| {
        fensu_policy::render_owned_skill(
            SKILL_OWNER,
            SKILL_IDENTITY,
            input_fingerprint,
            content.as_bytes(),
        )
        .map_err(value_error)
        .and_then(|value| String::from_utf8(value).map_err(value_error))
    })
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
    module.add_function(wrap_pyfunction!(render_owned_skill, module)?)?;
    module.add_function(wrap_pyfunction!(skill_freshness, module)?)?;
    Ok(())
}
