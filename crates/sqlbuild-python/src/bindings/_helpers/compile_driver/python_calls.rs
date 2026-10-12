//! Calling the Python stages the native driver still runs: imports, keyword calls and `with`.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::PyDict;

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
