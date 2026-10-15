//! The project-local compiler store root.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::compile_driver::python_calls::imported;

const FRONTIER_CONSTANTS_MODULE: &str = "sqlbuild.compiler.frontier.constants";

/// `project_dir / target / cache / compiler<suffix>`, keeping the path type of `project_dir`.
pub(crate) fn cache_directory<'py>(project_dir: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project_dir.py();
    let constant = |name: &str| -> PyResult<String> {
        imported(py, FRONTIER_CONSTANTS_MODULE, name)?.extract()
    };
    let store: String = format!(
        "{}{}",
        constant("COMPILER_CACHE_DIRECTORY_NAME")?,
        constant("NATIVE_CACHE_NAMESPACE_SUFFIX")?
    );
    project_dir
        .div(constant("TARGET_DIRECTORY_NAME")?)?
        .div(constant("CACHE_DIRECTORY_NAME")?)?
        .div(store)
}

/// Return the project's compiler store root.
#[pyfunction]
fn compiler_cache_directory<'py>(project_dir: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    cache_directory(project_dir)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(compiler_cache_directory, module)?)
}
