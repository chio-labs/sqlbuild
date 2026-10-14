//! The effective connection, settings and vars of a project, its local config and target.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::pyfunction;
use pyo3::types::{PyDict, PyList};

use sqlbuild_model_config::templates::models::TemplateOptions;

use crate::bindings::_helpers::compile_driver::python_calls::imported;
use crate::bindings::_helpers::model_config::template_data::{
    expanded_effective_vars, expanded_template_data,
};

const NATIVE_MODULE: &str = "sqlbuild._native";
const COMPILE_ERRORS_MODULE: &str = "sqlbuild.compiler.compile.exceptions";
const CONTRACT_MODELS_MODULE: &str = "sqlbuild.spec.contracts.models";
const CONNECTION_LABEL: &str = "effective connection";

/// Merge base project connection with the selected environment overrides.
#[pyfunction]
#[pyo3(signature = (*, project_config, local_config, target_config, effective_vars))]
pub(crate) fn build_effective_connection<'py>(
    project_config: &Bound<'py, PyAny>,
    local_config: &Bound<'py, PyAny>,
    target_config: &Bound<'py, PyAny>,
    effective_vars: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project_config.py();
    let (connection, error): (Bound<'py, PyAny>, Option<String>) =
        imported(py, NATIVE_MODULE, "effective_config_connection")?
            .call1((project_config, local_config, target_config))?
            .extract()?;
    if connection.is_none() {
        let raised: Bound<'py, PyAny> = imported(py, COMPILE_ERRORS_MODULE, "CompileInputError")?
            .call1((error.unwrap_or_default(),))?;
        return Err(PyErr::from_value(raised));
    }
    expanded_template_data(
        &connection,
        (effective_vars.downcast()?, &PyDict::new(py)),
        (
            TemplateOptions {
                allow_context: false,
                preserve_context_tokens: false,
                preserve_unknown_context: false,
            },
            CONNECTION_LABEL,
        ),
    )
}

/// Merge project settings with local developer overrides.
#[pyfunction]
#[pyo3(signature = (*, project_config, local_config))]
pub(crate) fn build_effective_settings<'py>(
    project_config: &Bound<'py, PyAny>,
    local_config: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project_config.py();
    let settings_class: Bound<'py, PyAny> = imported(py, CONTRACT_MODELS_MODULE, "SettingsConfig")?;
    let names: Vec<Bound<'py, PyAny>> = imported(py, "dataclasses", "fields")?
        .call1((&settings_class,))?
        .try_iter()?
        .map(|field| field?.getattr("name"))
        .collect::<PyResult<_>>()?;
    let values: Bound<'py, PyDict> = imported(py, NATIVE_MODULE, "effective_config_settings")?
        .call1((
            (
                project_config.getattr("settings")?,
                local_config.getattr("settings")?,
            ),
            local_config.getattr("setting_overrides")?,
            PyList::new(py, names)?,
        ))?
        .downcast_into()?;
    settings_class.call((), Some(&values))
}

/// Merge effective vars using the locked precedence order.
#[pyfunction]
#[pyo3(signature = (*, project_config, local_config, target_config, cli_vars))]
pub(crate) fn build_effective_vars<'py>(
    project_config: &Bound<'py, PyAny>,
    local_config: &Bound<'py, PyAny>,
    target_config: &Bound<'py, PyAny>,
    cli_vars: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project_config.py();
    let merged: Bound<'py, PyAny> = imported(py, NATIVE_MODULE, "effective_config_vars")?
        .call1(((project_config, local_config), target_config, cli_vars))?;
    expanded_effective_vars(merged.downcast()?)
}

/// `build_effective_vars` for a discovered project and target, without CLI vars.
pub(crate) fn project_vars<'py>(
    discovered: &Bound<'py, PyAny>,
    target_config: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    build_effective_vars(
        &discovered.getattr("project_config")?,
        &discovered.getattr("local_config")?,
        target_config,
        PyDict::new(discovered.py()).as_any(),
    )
}
