//! Compiled dynamic column family `name_pattern`s for matching runtime column names.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyclass, pymethods};
use sqlbuild_model_config::name_patterns::main::compile_name_pattern::compile_name_pattern;
use sqlbuild_model_config::name_patterns::models::NamePattern;

/// A `name_pattern` compiled to match whole column names; an invalid pattern raises `ValueError`.
#[pyclass(name = "NamePattern", module = "sqlbuild._native", frozen)]
struct PyNamePattern {
    pattern: NamePattern,
}

#[pymethods]
impl PyNamePattern {
    #[new]
    fn new(pattern: &str) -> PyResult<Self> {
        compile_name_pattern(pattern)
            .map(|pattern| Self { pattern })
            .map_err(|error| PyValueError::new_err(format!("invalid name_pattern: {error}")))
    }

    /// Whether `column_name` wholly matches the pattern.
    fn matches(&self, column_name: &str) -> bool {
        self.pattern.matches(column_name)
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<PyNamePattern>()
}
