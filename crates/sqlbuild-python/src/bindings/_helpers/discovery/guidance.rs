//! Setting guidance shown by diagnostics that depend on project settings.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_config::project::main::explicit_references_help::explicit_references_help as references_help;
use sqlbuild_config::project::main::microbatch_guidance::microbatch_guidance as concurrency_guidance;
use sqlbuild_config::project::main::sql_analysis_off_guidance::sql_analysis_off_guidance as analysis_off;

const SQL_ANALYSIS_KEY: &str = "sql_analysis";

/// The note and help for turning SQL analysis on, or `None` when it is effectively on.
pub(crate) fn sql_analysis_guidance(
    discovered_inputs: &Bound<'_, PyAny>,
    purpose: &str,
) -> PyResult<Option<(String, String)>> {
    let local: Bound<'_, PyAny> = discovered_inputs.getattr("local_config")?;
    let local_override: bool = local
        .getattr("setting_overrides")?
        .contains(SQL_ANALYSIS_KEY)?;
    let owner: Bound<'_, PyAny> = if local_override {
        local
    } else {
        discovered_inputs.getattr("project_config")?
    };
    if owner
        .getattr("settings")?
        .getattr(SQL_ANALYSIS_KEY)?
        .is_truthy()?
    {
        return Ok(None);
    }
    Ok(Some(analysis_off(local_override, purpose)))
}

#[pyfunction]
#[pyo3(signature = (*, discovered_inputs, purpose))]
fn sql_analysis_off_guidance(
    discovered_inputs: &Bound<'_, PyAny>,
    purpose: &str,
) -> PyResult<Option<(String, String)>> {
    sql_analysis_guidance(discovered_inputs, purpose)
}

#[pyfunction]
fn microbatch_guidance() -> (String, String) {
    concurrency_guidance()
}

#[pyfunction]
#[pyo3(signature = (*, allowed))]
fn explicit_references_help(allowed: &str) -> String {
    references_help(allowed)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(sql_analysis_off_guidance, module)?)?;
    module.add_function(wrap_pyfunction!(microbatch_guidance, module)?)?;
    module.add_function(wrap_pyfunction!(explicit_references_help, module)?)?;
    Ok(())
}
