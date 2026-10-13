//! The native config builder, validator and inherited storage policies of one compile.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::pyfunction;
use pyo3::types::{PyDict, PyDictMethods, PyString, PyTuple};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::compiled_project::loop_classes::table_backed;

const NATIVE_MODULE: &str = "sqlbuild._native";
const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const DISCOVERY_MODELS_MODULE: &str = "sqlbuild.compiler.discovery.models";
const UNICODE_ENVIRONMENT_MODULE: &str = "sqlbuild.compiler.compile.classes.unicode_environment";
const RETENTION_MODULE: &str = "sqlbuild.compiler.compile._helpers.config.retention";
const TABLE_TYPE_MODULE: &str = "sqlbuild.compiler.compile._helpers.config.table_type";
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
            (
                inputs.getattr("effective_vars")?,
                imported(py, UNICODE_ENVIRONMENT_MODULE, "UnicodeEnvironment")?.call0()?,
            ),
            (
                (
                    inputs.getattr("effective_target_name")?,
                    inputs.getattr("run_id")?,
                ),
                target_namespace,
            ),
        ))?;
    let inherited: Bound<'py, PyDict> = PyDict::new(py);
    let empty_name: Bound<'py, PyAny> = PyString::new(py, "").into_any();
    let mut materializations: Vec<Bound<'py, PyAny>> = vec![py.None().into_bound(py)];
    materializations.extend(table_backed(py)?);
    for materialized in materializations {
        let policy = |module: &str, name: &str| -> PyResult<Bound<'py, PyAny>> {
            call_with(
                &imported(py, module, name)?,
                &[
                    ("materialized", materialized.clone()),
                    ("model_value", py.None().into_bound(py)),
                    ("materialization_defaults", materialization_defaults.clone()),
                    ("target_config", target.clone()),
                    ("model_name", empty_name.clone()),
                ],
            )
        };
        let retention: Bound<'py, PyAny> =
            policy(RETENTION_MODULE, "resolve_time_travel_retention")?;
        let table_type: Bound<'py, PyAny> = policy(TABLE_TYPE_MODULE, "resolve_table_type")?;
        inherited.set_item(&materialized, (retention, table_type))?;
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
