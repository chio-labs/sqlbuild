//! The interpreter-exit signal native waits poll so Python daemon threads leave native frames before finalization.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::sync::PyOnceLock;

use crate::bindings::_helpers::boundary::python_calls::imported;

static EXIT_SIGNAL: PyOnceLock<Py<PyAny>> = PyOnceLock::new();

/// The process-wide `threading.Event` set once interpreter exit begins.
fn exit_signal(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    EXIT_SIGNAL
        .get_or_try_init(py, || {
            imported(py, "threading", "Event")?
                .call0()
                .map(Bound::unbind)
        })
        .map(|signal| signal.bind(py).clone())
}

/// Whether an exit hook has started stopping native daemon threads.
pub(crate) fn interpreter_exiting(py: Python<'_>) -> PyResult<bool> {
    exit_signal(py)?.call_method0("is_set")?.is_truthy()
}

/// Tell every native wait to stop waiting on Python work that may outlive the interpreter.
pub(crate) fn signal_interpreter_exit(py: Python<'_>) -> PyResult<()> {
    exit_signal(py)?.call_method0("set")?;
    Ok(())
}
