//! Collect compile diagnostics so one compile reports every violation, not only the first.

use std::sync::Mutex;

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use pyo3::{PyErr, pyclass, pyfunction, pymethods, wrap_pyfunction};

use crate::bindings::_helpers::compile_driver::python_calls::imported;

const COMPILE_ERRORS_MODULE: &str = "sqlbuild.compiler.compile.exceptions";
const CONTEXT_VARIABLE_NAME: &str = "sqlbuild_collected_compile_diagnostics";

static ACTIVE_COLLECTOR: PyOnceLock<Py<PyAny>> = PyOnceLock::new();

/// The context variable holding the collection diagnostics are reported into, if any.
fn active_collector(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    ACTIVE_COLLECTOR
        .get_or_try_init(py, || {
            let keywords: Bound<'_, PyDict> = PyDict::new(py);
            keywords.set_item("default", py.None())?;
            imported(py, "contextvars", "ContextVar")?
                .call((CONTEXT_VARIABLE_NAME,), Some(&keywords))
                .map(Bound::unbind)
        })
        .map(|variable| variable.bind(py).clone())
}

/// Deduplicated compile diagnostics gathered while the collection is entered.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct CollectedCompileDiagnostics {
    by_key: Py<PyDict>,
    token: Mutex<Option<Py<PyAny>>>,
}

#[pymethods]
impl CollectedCompileDiagnostics {
    fn __enter__<'py>(slf: &Bound<'py, Self>) -> PyResult<Bound<'py, Self>> {
        let token: Bound<'_, PyAny> =
            active_collector(slf.py())?.call_method1("set", (slf.clone(),))?;
        *slf.get()
            .token
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner) = Some(token.unbind());
        Ok(slf.clone())
    }

    #[pyo3(signature = (*_exception))]
    fn __exit__(&self, py: Python<'_>, _exception: &Bound<'_, PyTuple>) -> PyResult<bool> {
        let token: Option<Py<PyAny>> = self
            .token
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .take();
        if let Some(token) = token {
            active_collector(py)?.call_method1("reset", (token,))?;
        }
        Ok(false)
    }

    /// Record one diagnostic; a repeated key keeps the first diagnostic.
    #[pyo3(signature = (*, key, diagnostic))]
    fn add(
        &self,
        py: Python<'_>,
        key: &Bound<'_, PyAny>,
        diagnostic: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        self.by_key
            .bind(py)
            .call_method1("setdefault", (key, diagnostic))?;
        Ok(())
    }

    /// The recorded diagnostics in deterministic key order.
    #[getter]
    fn diagnostics<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        let by_key: &Bound<'py, PyDict> = self.by_key.bind(py);
        let keys: Bound<'py, PyAny> = imported(py, "builtins", "sorted")?.call1((by_key,))?;
        let diagnostics: Vec<Bound<'py, PyAny>> = keys
            .try_iter()?
            .map(|key| by_key.as_any().get_item(key?))
            .collect::<PyResult<_>>()?;
        PyTuple::new(py, diagnostics)
    }
}

/// A new collection; entering it collects diagnostics instead of raising the first one.
#[pyfunction]
pub(crate) fn collect_compile_diagnostics(
    py: Python<'_>,
) -> PyResult<Bound<'_, CollectedCompileDiagnostics>> {
    Bound::new(
        py,
        CollectedCompileDiagnostics {
            by_key: PyDict::new(py).unbind(),
            token: Mutex::new(None),
        },
    )
}

/// Record a diagnostic in the active collection, or raise it when none is active.
#[pyfunction]
#[pyo3(signature = (*, key, diagnostic))]
pub(crate) fn report_compile_diagnostic(
    key: &Bound<'_, PyAny>,
    diagnostic: &Bound<'_, PyAny>,
) -> PyResult<()> {
    let py: Python<'_> = key.py();
    let collector: Bound<'_, PyAny> = active_collector(py)?.call_method0("get")?;
    if let Ok(collector) = collector.cast::<CollectedCompileDiagnostics>() {
        return collector.get().add(py, key, diagnostic);
    }
    let location: Bound<'_, PyAny> = diagnostic.getattr("location")?;
    let path: Bound<'_, PyAny> = diagnostic.getattr("path")?;
    let pointer: String = if !location.is_none() {
        format!(
            "\n  --> {}:{}",
            location.getattr("path")?.call_method0("as_posix")?.str()?,
            location.getattr("line")?.str()?
        )
    } else if !path.is_none() {
        format!("\n  --> {}", path.call_method0("as_posix")?.str()?)
    } else {
        String::new()
    };
    let keywords: Bound<'_, PyDict> = PyDict::new(py);
    keywords.set_item("code", diagnostic.getattr("code")?)?;
    keywords.set_item("help", diagnostic.getattr("help")?)?;
    let message: String = format!("{}{pointer}", diagnostic.getattr("message")?.str()?);
    Err(PyErr::from_value(
        imported(py, COMPILE_ERRORS_MODULE, "CompileInputError")?
            .call((message,), Some(&keywords))?,
    ))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<CollectedCompileDiagnostics>()?;
    module.add_function(wrap_pyfunction!(collect_compile_diagnostics, module)?)?;
    module.add_function(wrap_pyfunction!(report_compile_diagnostic, module)?)
}
