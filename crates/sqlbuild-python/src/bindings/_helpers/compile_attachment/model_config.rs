//! The native config builder, validator and inherited storage policies of one compile.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::pyfunction;
use pyo3::types::{PyDict, PyDictMethods, PyTuple};

use crate::bindings::_helpers::compile_attachment::storage_policies::inherited_storage;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::compiled_project::loop_classes::table_backed;
use crate::bindings::_helpers::model_config::unicode_environment::unicode_environment;

const NATIVE_MODULE: &str = "sqlbuild._native";
const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const DISCOVERY_MODELS_MODULE: &str = "sqlbuild.compiler.discovery.models";
const CONTRACT_MODELS_MODULE: &str = "sqlbuild.spec.contracts.models";

/// Capture the project inputs every model's native config build and validation read.
#[pyfunction]
#[pyo3(signature = (*, inputs, validator))]
pub(crate) fn native_model_config_session<'py>(
    inputs: &Bound<'py, PyAny>,
    validator: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = inputs.py();
    let project_config: Bound<'py, PyAny> = inputs.getattr("project_config")?;
    let target: Bound<'py, PyAny> = inputs.getattr("target_config")?;
    let declared: Bound<'py, PyAny> = project_config.getattr("materialization_defaults")?;
    let materialization_defaults: Bound<'py, PyAny> = if declared.is_truthy()? {
        declared
    } else {
        imported(py, CONTRACT_MODELS_MODULE, "MaterializationDefaultsConfig")?.call0()?
    };
    let hook_entries: Bound<'py, PyTuple> = PyTuple::new(
        py,
        ["SqlHookEntry", "NamedSqlHookEntry", "PythonHookEntry"]
            .iter()
            .map(|name| imported(py, DISCOVERY_MODELS_MODULE, name))
            .collect::<PyResult<Vec<_>>>()?,
    )?;
    let target_namespace: Bound<'py, PyAny> = if target.is_none() {
        target.clone()
    } else {
        PyTuple::new(py, [target.getattr("database")?, target.getattr("schema")?])?.into_any()
    };
    let builder: Bound<'py, PyAny> = imported(py, NATIVE_MODULE, "NativeModelConfigBuilder")?
        .call1((
            (
                project_config.getattr("defaults")?,
                project_config.getattr("path_defaults")?,
                hook_entries,
            ),
            (inputs.getattr("effective_vars")?, unicode_environment(py)?),
            (
                (
                    inputs.getattr("effective_target_name")?,
                    inputs.getattr("run_id")?,
                ),
                target_namespace,
            ),
        ))?;
    let inherited: Bound<'py, PyDict> = PyDict::new(py);
    let mut materializations: Vec<Bound<'py, PyAny>> = vec![py.None().into_bound(py)];
    materializations.extend(table_backed(py)?);
    for materialized in materializations {
        let storage: Bound<'py, PyTuple> =
            inherited_storage(&materialized, &materialization_defaults, &target)?;
        inherited.set_item(&materialized, storage)?;
    }
    call_with(
        &imported(py, COMPILE_MODELS_MODULE, "NativeModelConfigSession")?,
        &[
            ("path_defaults", project_config.getattr("path_defaults")?),
            ("builder", builder),
            ("validator", validator.clone()),
            ("inherited_storage", inherited.into_any()),
        ],
    )
}
