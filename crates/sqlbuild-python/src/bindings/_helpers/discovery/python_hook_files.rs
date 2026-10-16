//! The Python hook files of every hook role, listed natively for the Python module loader.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_discovery::declaration_files::main::python_hook_files::python_hook_files;
use sqlbuild_discovery::declaration_files::models::{
    CollectionFailure, DiscoverySession, FileScope,
};
use sqlbuild_discovery::tree::models::ProjectTree;

use crate::bindings::_helpers::discovery::declaration_records::{
    add_scope_fields, discovery_session, path_class,
};
use crate::bindings::_helpers::discovery::project_files::path_object;
use crate::bindings::_helpers::discovery::raised::{failure_error, stage_error};
use crate::bindings::_helpers::discovery::snapshot::{in_snapshot, project_tree};
use crate::bindings::models::{NativeDiscoverySession, NativeProjectTree};

/// Each public Python hook file as `file_path`, `relative_path` and its role's scope fields.
#[pyfunction]
#[pyo3(signature = (*, project_dir))]
pub(crate) fn discover_python_hook_files<'py>(
    project_dir: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    in_snapshot(project_dir, || {
        let py: Python<'py> = project_dir.py();
        let tree: Bound<'py, NativeProjectTree> = project_tree(project_dir)?;
        let session: Bound<'py, NativeDiscoverySession> = discovery_session(project_dir)?;
        let inner: &ProjectTree = &tree.get().inner;
        let discovery: &DiscoverySession = &session.get().inner;
        let listed: Vec<(String, FileScope)> =
            match py.detach(|| python_hook_files(discovery, inner)) {
                Ok(listed) => listed,
                Err(CollectionFailure::Stage(failure)) => {
                    return Err(stage_error(inner, project_dir, failure));
                }
                Err(CollectionFailure::Layout(failure)) => return Err(failure_error(py, failure)),
            };
        let mut files: Vec<Bound<'py, PyDict>> = Vec::with_capacity(listed.len());
        for (relative_path, scope) in listed {
            let relative: Bound<'py, PyAny> =
                path_class(py)?.call1((path_object(py, inner, relative_path)?,))?;
            let fields: Bound<'py, PyDict> = PyDict::new(py);
            fields.set_item("file_path", project_dir.div(&relative)?)?;
            fields.set_item("relative_path", relative)?;
            add_scope_fields(inner, &scope, &fields)?;
            files.push(fields);
        }
        PyTuple::new(py, files)
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(discover_python_hook_files, module)?)
}
