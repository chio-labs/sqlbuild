//! Project inputs holding only the project and local configuration.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::PyString;

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, within};

const NATIVE_MODULE: &str = "sqlbuild._native";
const DISCOVERY_MODELS_MODULE: &str = "sqlbuild.compiler.discovery.models";
const LIFECYCLE_MODULE: &str = "sqlbuild.runtime.observability.classes.operation_lifecycle";

/// `DiscoveredProjectInputs` with the loaded configuration, inside the project discovery lifecycle.
pub(crate) fn discover_project_configuration<'py>(
    py: Python<'py>,
    project_dir: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let lifecycle: Bound<'py, PyAny> = call_with(
        &imported(py, LIFECYCLE_MODULE, "OperationLifecycle")?,
        &[
            ("operation_kind", PyString::new(py, "project").into_any()),
            (
                "operation_name",
                PyString::new(py, "project_discovery").into_any(),
            ),
        ],
    )?;
    within(&lifecycle, |_| {
        call_with(
            &imported(py, DISCOVERY_MODELS_MODULE, "DiscoveredProjectInputs")?,
            &[
                ("project_dir", project_dir.clone()),
                (
                    "project_config",
                    imported(py, NATIVE_MODULE, "load_project_config_file")?
                        .call1((project_dir,))?,
                ),
                (
                    "local_config",
                    imported(py, NATIVE_MODULE, "load_local_config_file")?.call1((project_dir,))?,
                ),
            ],
        )
    })
}
