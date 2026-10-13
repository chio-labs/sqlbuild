//! Keyword-only native function arguments read from `**request`.

use pyo3::exceptions::PyTypeError;
use pyo3::prelude::{Bound, PyAny, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods};

/// Keyword arguments of one call, each required.
pub(crate) struct Request<'a, 'py> {
    function: &'static str,
    arguments: Option<&'a Bound<'py, PyDict>>,
    py: Python<'py>,
}

impl<'a, 'py> Request<'a, 'py> {
    pub(crate) fn new(
        function: &'static str,
        arguments: Option<&'a Bound<'py, PyDict>>,
    ) -> PyResult<Self> {
        let py: Python<'py> = match arguments {
            Some(arguments) => arguments.py(),
            None => {
                return Err(PyTypeError::new_err(format!(
                    "{function}() missing required keyword-only arguments"
                )));
            }
        };
        Ok(Self {
            function,
            arguments,
            py,
        })
    }

    pub(crate) fn py(&self) -> Python<'py> {
        self.py
    }

    pub(crate) fn get(&self, name: &str) -> PyResult<Bound<'py, PyAny>> {
        let value: Option<Bound<'py, PyAny>> = match self.arguments {
            Some(arguments) => arguments.get_item(name)?,
            None => None,
        };
        value.ok_or_else(|| {
            PyTypeError::new_err(format!(
                "{}() missing 1 required keyword-only argument: '{name}'",
                self.function
            ))
        })
    }

    /// The argument, or `None` when the caller left it out.
    pub(crate) fn optional(&self, name: &str) -> PyResult<Option<Bound<'py, PyAny>>> {
        match self.arguments {
            Some(arguments) => arguments.get_item(name),
            None => Ok(None),
        }
    }
}
