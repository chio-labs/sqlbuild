//! Model description resolution for header-only tooling, without importing project Python.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyBool, PyCFunction, PyFrozenSet};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, within};
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;

/// Models and model schemas, skipping files that cannot be read.
#[pyfunction]
#[pyo3(signature = (*, project_dir))]
pub(crate) fn discover_model_description_inputs<'py>(
    project_dir: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project_dir.py();
    let native = |name: NativeAttr| registry::native(py, name);
    let project_config: Bound<'py, PyAny> =
        native(NativeAttr::LoadProjectConfigFile)?.call1((project_dir,))?;
    let skip: Bound<'py, PyAny> =
        PyCFunction::new_closure(py, None, None, |_arguments, _keywords| -> PyResult<()> {
            Ok(())
        })?
        .into_any();
    let disabled: Bound<'py, PyAny> = PyBool::new(py, false).to_owned().into_any();
    let scope: Bound<'py, PyAny> = call_with(
        &native(NativeAttr::DirectorySnapshotScope)?,
        &[("project_dir", project_dir.clone())],
    )?;
    within(&scope, |_| {
        call_with(
            &registry::class(py, RecordId::DiscoveredProjectInputs)?,
            &[
                ("project_config", project_config),
                (
                    "local_config",
                    registry::class(py, RecordId::LocalConfig)?.call0()?,
                ),
                (
                    "model_files",
                    call_with(
                        &native(NativeAttr::DiscoverModelFiles)?,
                        &[
                            ("project_dir", project_dir.clone()),
                            ("extract_implicit_alias_columns", disabled.clone()),
                            ("extract_output_column_locations", disabled),
                            ("on_fault", skip.clone()),
                        ],
                    )?,
                ),
                (
                    "model_schema_files",
                    call_with(
                        &native(NativeAttr::DiscoverModelSchemaFiles)?,
                        &[("project_dir", project_dir.clone()), ("on_fault", skip)],
                    )?,
                ),
            ],
        )
    })
}

/// Model files that `[defaults]`, `[path_defaults]` or a model schema describe.
pub(crate) fn externally_described_models<'py>(
    project_dir: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyFrozenSet>> {
    let py: Python<'py> = project_dir.py();
    let inputs: Bound<'py, PyAny> = discover_model_description_inputs(project_dir)?;
    let schemas: Bound<'py, PyAny> =
        registry::native(py, NativeAttr::PublicModelSchemaIndex)?.call1((&inputs,))?;
    let described: Bound<'py, PyAny> =
        registry::native(py, NativeAttr::ExternallyDescribedModels)?.call1((&inputs, schemas))?;
    PyFrozenSet::new(py, described.try_iter()?.collect::<PyResult<Vec<_>>>()?)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(discover_model_description_inputs, module)?)?;
    Ok(())
}
