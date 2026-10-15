//! The resource and model facts the native project assembly hands to the compile driver.

use pyo3::prelude::{Py, PyAny};
use pyo3::pyclass;

/// Per-resource facts in input order, and whether each model's SQL passed syntax validation.
#[pyclass(module = "sqlbuild._native", frozen, get_all)]
#[derive(Debug)]
pub(crate) struct NativeProjectResources {
    pub(crate) model_deps: Py<PyAny>,
    pub(crate) model_syntax_valid: Py<PyAny>,
    pub(crate) source_namespaces: Py<PyAny>,
    pub(crate) seed_namespaces: Py<PyAny>,
    pub(crate) function_deps: Py<PyAny>,
    pub(crate) audit_scope_deps: Py<PyAny>,
    /// The `NativeResourceFailure` Python's assembly raises at, or `None`.
    pub(crate) failure: Py<PyAny>,
}

/// The resource Python's assembly raises at, and the exception it raises there.
#[pyclass(module = "sqlbuild._native", frozen, get_all)]
#[derive(Debug)]
pub(crate) struct NativeResourceFailure {
    pub(crate) slot: Py<PyAny>,
    pub(crate) index: Py<PyAny>,
    pub(crate) error: Py<PyAny>,
}

/// One model's native facts; its dependencies as `(resource type, name)` rows.
#[pyclass(module = "sqlbuild._native", frozen, get_all)]
#[derive(Debug)]
pub(crate) struct NativeModelFacts {
    pub(crate) deps: Py<PyAny>,
    pub(crate) dynamic_contract: Py<PyAny>,
    pub(crate) syntax_valid: Py<PyAny>,
}

/// Every model's native facts and the resource facts.
#[pyclass(module = "sqlbuild._native", frozen, get_all)]
#[derive(Debug)]
pub(crate) struct NativeProjectFacts {
    pub(crate) models: Py<PyAny>,
    pub(crate) resources: Py<PyAny>,
}
