//! Calling the Python stages the native driver still runs: imports, keyword calls and `with`.

use pyo3::exceptions::PyTypeError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString};

/// `module.name`, imported.
pub(crate) fn imported<'py>(
    py: Python<'py>,
    module: &str,
    name: &str,
) -> PyResult<Bound<'py, PyAny>> {
    py.import(module)?.getattr(name)
}

/// Keyword arguments built from `(name, value)` pairs, in order.
pub(crate) fn keywords<'py>(
    py: Python<'py>,
    pairs: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyDict>> {
    let arguments: Bound<'py, PyDict> = PyDict::new(py);
    for (name, value) in pairs {
        arguments.set_item(*name, value)?;
    }
    Ok(arguments)
}

/// `callable(**pairs)`.
pub(crate) fn call_with<'py>(
    callable: &Bound<'py, PyAny>,
    pairs: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    callable.call((), Some(&keywords(callable.py(), pairs)?))
}

/// Run `body` inside `with manager as entered:`; managers here never suppress exceptions.
pub(crate) fn within<'py, T>(
    manager: &Bound<'py, PyAny>,
    body: impl FnOnce(&Bound<'py, PyAny>) -> PyResult<T>,
) -> PyResult<T> {
    let py: Python<'py> = manager.py();
    let entered: Bound<'py, PyAny> = manager.call_method0("__enter__")?;
    match body(&entered) {
        Ok(value) => {
            manager.call_method1("__exit__", (py.None(), py.None(), py.None()))?;
            Ok(value)
        }
        Err(error) => {
            manager.call_method1(
                "__exit__",
                (error.get_type(py), error.value(py), error.traceback(py)),
            )?;
            Err(error)
        }
    }
}

/// The transient status line, when one is shown.
pub(crate) struct Status<'py>(pub(crate) Bound<'py, PyAny>);

impl Status<'_> {
    pub(crate) fn start(&self, message: &str) -> PyResult<()> {
        if !self.0.is_none() {
            self.0.call_method1("start", (message,))?;
        }
        Ok(())
    }

    pub(crate) fn complete(&self, message: &str) -> PyResult<()> {
        if !self.0.is_none() {
            call_with(
                &self.0.getattr("complete")?,
                &[("message", PyString::new(self.0.py(), message).into_any())],
            )?;
        }
        Ok(())
    }
}

/// Keyword-only arguments of a driver entry point, checked as Python checks a signature.
pub(crate) struct KeywordArguments<'py> {
    values: Bound<'py, PyDict>,
}

impl<'py> KeywordArguments<'py> {
    /// Accept `options` for `function`, rejecting missing `required` and unknown names.
    pub(crate) fn read(
        py: Python<'py>,
        function: &str,
        options: Option<Bound<'py, PyDict>>,
        (required, optional): (&[&str], &[&str]),
    ) -> PyResult<Self> {
        let values: Bound<'py, PyDict> = options.unwrap_or_else(|| PyDict::new(py));
        for name in values.keys() {
            let name: String = name.extract()?;
            if !required.contains(&name.as_str()) && !optional.contains(&name.as_str()) {
                return Err(PyTypeError::new_err(format!(
                    "{function}() got an unexpected keyword argument '{name}'"
                )));
            }
        }
        for name in required {
            if !values.contains(*name)? {
                return Err(PyTypeError::new_err(format!(
                    "{function}() missing 1 required keyword-only argument: '{name}'"
                )));
            }
        }
        Ok(Self { values })
    }

    /// The argument `name`, or `None` when it was not passed.
    pub(crate) fn value(&self, name: &str) -> PyResult<Bound<'py, PyAny>> {
        let py: Python<'py> = self.values.py();
        Ok(self
            .values
            .get_item(name)?
            .unwrap_or_else(|| py.None().into_bound(py)))
    }

    /// The argument `name` as a truth value, `False` when it was not passed.
    pub(crate) fn flag(&self, name: &str) -> PyResult<bool> {
        self.value(name)?.is_truthy()
    }

    /// Whether `name` was passed.
    pub(crate) fn passed(&self, name: &str) -> PyResult<bool> {
        self.values.contains(name)
    }
}
