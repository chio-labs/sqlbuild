//! The project directory, its discovered inputs and its adapter.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};

use crate::bindings::_helpers::command_runtime::adapters::resolve_cli_adapter;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};

const NATIVE_MODULE: &str = "sqlbuild._native";
const ADAPTER_NAME_MODULE: &str = "sqlbuild._native";

/// The project directory, defaulting to the working directory, with its inputs and adapter.
pub(crate) struct ProjectAdapter<'py> {
    pub(crate) project_dir: Bound<'py, PyAny>,
    pub(crate) discovered: Bound<'py, PyAny>,
    pub(crate) adapter: Bound<'py, PyAny>,
}

pub(crate) fn project_adapter<'py>(
    py: Python<'py>,
    project_dir: Option<Bound<'py, PyAny>>,
) -> PyResult<ProjectAdapter<'py>> {
    let project_dir: Bound<'py, PyAny> = match project_dir.filter(|path| !path.is_none()) {
        Some(path) => path,
        None => imported(py, "pathlib", "Path")?.call_method0("cwd")?,
    };
    let discovered: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "discover_project_inputs")?,
        &[("project_dir", project_dir.clone())],
    )?;
    let adapter_name: Bound<'py, PyAny> = call_with(
        &imported(py, ADAPTER_NAME_MODULE, "resolve_effective_adapter_name")?,
        &[
            ("project_config", discovered.getattr("project_config")?),
            ("local_config", discovered.getattr("local_config")?),
        ],
    )?;
    let adapter: Bound<'py, PyAny> = resolve_cli_adapter(&adapter_name, &project_dir)?;
    Ok(ProjectAdapter {
        project_dir,
        discovered,
        adapter,
    })
}
