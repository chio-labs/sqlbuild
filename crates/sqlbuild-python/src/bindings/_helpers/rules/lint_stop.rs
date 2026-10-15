//! The stop signal that lets a speculative lint run be abandoned between files.

use std::sync::{Mutex, PoisonError};

use pyo3::prelude::{
    Bound, Py, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::sync::PyOnceLock;
use pyo3::types::PyTuple;
use pyo3::{pyclass, pyfunction, pymethods, wrap_pyfunction};

use crate::bindings::_helpers::compile_driver::python_calls::{context_variable, imported};

const LINT_EXCEPTIONS_MODULE: &str = "sqlbuild._native";
const STOP_VARIABLE: &str = "active_lint_stop";

static ACTIVE_STOP: PyOnceLock<Py<PyAny>> = PyOnceLock::new();

/// The context variable holding the active lint run's stop event, if any.
fn active_stop_variable(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    context_variable(py, &ACTIVE_STOP, STOP_VARIABLE)
}

/// Abandon a speculative lint run on this thread once its owner no longer needs it.
pub(crate) fn check_stop(py: Python<'_>) -> PyResult<()> {
    let stop: Bound<'_, PyAny> = active_stop_variable(py)?.call_method0("get")?;
    if !stop.is_none() && stop.call_method0("is_set")?.is_truthy()? {
        return Err(PyErr::from_value(
            imported(py, LINT_EXCEPTIONS_MODULE, "LintStoppedError")?.call0()?,
        ));
    }
    Ok(())
}

/// Makes `stop` the active lint stop event while entered.
#[pyclass(frozen, module = "sqlbuild._native")]
struct LintStopScope {
    stop: Py<PyAny>,
    token: Mutex<Option<Py<PyAny>>>,
}

#[pymethods]
impl LintStopScope {
    fn __enter__(&self, py: Python<'_>) -> PyResult<()> {
        let token: Bound<'_, PyAny> =
            active_stop_variable(py)?.call_method1("set", (self.stop.bind(py),))?;
        *self.token.lock().unwrap_or_else(PoisonError::into_inner) = Some(token.unbind());
        Ok(())
    }

    #[pyo3(signature = (*_exception))]
    fn __exit__(&self, py: Python<'_>, _exception: &Bound<'_, PyTuple>) -> PyResult<bool> {
        let token: Option<Py<PyAny>> = self
            .token
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .take();
        if let Some(token) = token {
            active_stop_variable(py)?.call_method1("reset", (token,))?;
        }
        Ok(false)
    }
}

/// A scope that makes `stop` the active lint stop event while entered.
#[pyfunction]
fn lint_stop_scope(stop: &Bound<'_, PyAny>) -> LintStopScope {
    LintStopScope {
        stop: stop.clone().unbind(),
        token: Mutex::new(None),
    }
}

/// The active lint run's stop event, or `None` outside a stop scope.
#[pyfunction]
fn active_lint_stop(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    active_stop_variable(py)?.call_method0("get")
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<LintStopScope>()?;
    module.add_function(wrap_pyfunction!(lint_stop_scope, module)?)?;
    module.add_function(wrap_pyfunction!(active_lint_stop, module)?)
}
