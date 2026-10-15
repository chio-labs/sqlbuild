//! Shared reads for imported project Python discovery: paths, shim calls and records.

use pyo3::exceptions::PyException;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyTuple};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::event_exporting::scope::current_scope;

pub(crate) const NATIVE_MODULE: &str = "sqlbuild._native";
pub(crate) const SHIM_MODULE: &str =
    "sqlbuild.compiler.discovery._helpers.filesystem.project_modules";
pub(crate) const MODELS_MODULE: &str = "sqlbuild.compiler.discovery.models";
pub(crate) const ERRORS_MODULE: &str = "sqlbuild._native";

/// One project directory under discovery.
pub(crate) struct ProjectDir<'py> {
    pub(crate) path: Bound<'py, PyAny>,
}

impl<'py> ProjectDir<'py> {
    pub(crate) fn py(&self) -> Python<'py> {
        self.path.py()
    }

    /// `project_dir / name`.
    pub(crate) fn child(&self, name: &str) -> PyResult<Bound<'py, PyAny>> {
        self.path.div(name)
    }

    /// `project_relative_path(path=file_path, project_dir=project_dir)`.
    pub(crate) fn relative(&self, file_path: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
        call_with(
            &imported(self.py(), NATIVE_MODULE, "project_relative_path")?,
            &[
                ("path", file_path.clone()),
                ("project_dir", self.path.clone()),
            ],
        )
    }

    /// `str(file_path.relative_to(project_dir))`.
    pub(crate) fn relative_to(&self, file_path: &Bound<'py, PyAny>) -> PyResult<String> {
        file_path
            .call_method1("relative_to", (&self.path,))?
            .str()?
            .extract()
    }

    /// Python files under `root`, in discovery order.
    pub(crate) fn module_files(
        &self,
        root: &str,
        public_only: bool,
    ) -> PyResult<Vec<Bound<'py, PyAny>>> {
        let py: Python<'py> = self.py();
        call_with(
            &imported(py, NATIVE_MODULE, "discover_python_module_files")?,
            &[
                ("project_dir", self.path.clone()),
                ("root", PyString::new(py, root).into_any()),
                (
                    "public_only",
                    pyo3::types::PyBool::new(py, public_only)
                        .to_owned()
                        .into_any(),
                ),
            ],
        )?
        .try_iter()?
        .collect()
    }

    /// `shim.<loader>(file_path=file_path, project_dir=project_dir)`.
    pub(crate) fn load(
        &self,
        loader: &str,
        file_path: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        call_with(
            &shim(self.py(), loader)?,
            &[
                ("file_path", file_path.clone()),
                ("project_dir", self.path.clone()),
            ],
        )
    }

    /// The cached providers, lifecycle sinks and output sinks of a warm command, if any.
    pub(crate) fn cached_extensions(&self) -> PyResult<Option<Bound<'py, PyAny>>> {
        let scope: Bound<'py, PyAny> = current_scope(self.py())?;
        if scope.is_none() {
            return Ok(None);
        }
        let cached: Bound<'py, PyAny> = call_with(
            &scope.getattr("cached_extensions")?,
            &[("project_dir", self.path.clone())],
        )?;
        Ok((!cached.is_none()).then_some(cached))
    }
}

/// `project_modules.<name>`.
pub(crate) fn shim<'py>(py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyAny>> {
    imported(py, SHIM_MODULE, name)
}

/// Functions defined in one loaded module.
pub(crate) fn module_functions<'py>(
    module: &Bound<'py, PyAny>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    shim(module.py(), "module_functions")?
        .call1((module,))?
        .try_iter()?
        .collect()
}

/// `sqlbuild.compiler.discovery.models.<class_name>(**pairs)`.
pub(crate) fn discovered<'py>(
    py: Python<'py>,
    class_name: &str,
    pairs: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    call_with(&imported(py, MODELS_MODULE, class_name)?, pairs)
}

/// `sqlbuild._native.<class_name>(message)`.
pub(crate) fn discovery_error(py: Python<'_>, class_name: &str, message: String) -> PyErr {
    imported(py, ERRORS_MODULE, class_name)
        .and_then(|class| class.call1((message,)))
        .map_or_else(|error| error, PyErr::from_value)
}

/// `discovery_error` raised from `cause`.
pub(crate) fn discovery_error_from(
    py: Python<'_>,
    (class_name, message): (&str, String),
    cause: PyErr,
) -> PyErr {
    let error: PyErr = discovery_error(py, class_name, message);
    error.set_cause(py, Some(cause));
    error
}

/// Whether `error` is an `Exception`, which discovery wraps; other exceptions propagate.
pub(crate) fn is_exception(py: Python<'_>, error: &PyErr) -> bool {
    error.is_instance_of::<PyException>(py)
}

/// `{provider.name: provider for provider in providers}`.
pub(crate) fn provider_by_name<'py>(providers: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let by_name: Bound<'py, PyDict> = PyDict::new(providers.py());
    for provider in providers.try_iter()? {
        let provider: Bound<'py, PyAny> = provider?;
        by_name.set_item(provider.getattr("name")?, provider)?;
    }
    Ok(by_name)
}

/// The provider parameters of one loaded user function.
pub(crate) fn provider_usages<'py>(
    function: &Bound<'py, PyAny>,
    provider_by_name: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyAny>> {
    call_with(
        &shim(function.py(), "provider_usages")?,
        &[
            ("function", function.clone()),
            ("provider_by_name", provider_by_name.clone().into_any()),
        ],
    )
}

/// A tuple of the given items.
pub(crate) fn tuple_of<'py>(
    py: Python<'py>,
    items: Vec<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    Ok(PyTuple::new(py, items)?.into_any())
}

/// `name` of the read definition, or `None` when the function carries no such definition.
pub(crate) fn definition<'py>(
    function: &Bound<'py, PyAny>,
    (module, reader): (&str, &str),
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let read: Bound<'py, PyAny> = imported(function.py(), module, reader)?.call1((function,))?;
    Ok((!read.is_none()).then_some(read))
}
