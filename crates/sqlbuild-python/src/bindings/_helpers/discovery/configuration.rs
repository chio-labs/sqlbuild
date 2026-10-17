//! Project inputs holding only the project and local configuration.

use pyo3::prelude::{Bound, PyAny, PyResult, Python};
use pyo3::types::PyString;

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, within};
use crate::bindings::_helpers::contracts::project_config::{
    load_local_config_file, load_project_config_file,
};
use crate::bindings::_helpers::native_host::executor::ExecutorHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::records::construct::new_record_with;
use crate::bindings::_helpers::records::ids::RecordId;

/// `DiscoveredProjectInputs` with the loaded configuration, inside the project discovery lifecycle.
pub(crate) fn discover_project_configuration<'py>(
    py: Python<'py>,
    project_dir: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let lifecycle: Bound<'py, PyAny> = call_with(
        &host::entry(py, ExecutorHost::OperationLifecycle)?,
        &[
            ("operation_kind", PyString::new(py, "project").into_any()),
            (
                "operation_name",
                PyString::new(py, "project_discovery").into_any(),
            ),
        ],
    )?;
    within(&lifecycle, |_| {
        new_record_with(
            py,
            RecordId::DiscoveredProjectInputs,
            &[
                ("project_dir", project_dir.clone()),
                (
                    "project_config",
                    load_project_config_file(py, project_dir)?.into_bound(py),
                ),
                (
                    "local_config",
                    load_local_config_file(py, project_dir)?.into_bound(py),
                ),
            ],
        )
    })
}
