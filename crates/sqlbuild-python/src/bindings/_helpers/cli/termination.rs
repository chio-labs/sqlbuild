//! SIGTERM as an interrupt: the command stops the way Ctrl+C stops it, records its end and exits with the conventional code.

use pyo3::create_exception;
use pyo3::exceptions::PyKeyboardInterrupt;
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyCFunction, PyDict, PyTuple};

use crate::bindings::_helpers::boundary::python_calls::imported;

create_exception!(
    sqlbuild._native,
    CommandTerminated,
    PyKeyboardInterrupt,
    "Raised in the main thread when the command receives SIGTERM; handled like Ctrl+C."
);

/// The number of SIGTERM, as POSIX defines it.
pub(crate) const SIGTERM_NUMBER: i64 = 15;
/// The number of SIGINT, which Python raises as `KeyboardInterrupt`.
pub(crate) const SIGINT_NUMBER: i64 = 2;
/// The exit code of a command stopped by SIGTERM: 128 plus the signal number.
pub(crate) const TERMINATED_EXIT_CODE: i64 = 128 + SIGTERM_NUMBER;
const TERMINATED_MESSAGE: &str = "terminated by SIGTERM";

/// The SIGTERM handler installed for one command, and the handler it replaced.
pub(crate) struct TerminationHandler<'py> {
    signal: Bound<'py, PyAny>,
    previous: Option<Bound<'py, PyAny>>,
}

impl Drop for TerminationHandler<'_> {
    fn drop(&mut self) {
        if let Some(previous) = self.previous.take() {
            let number: PyResult<Bound<'_, PyAny>> = self.signal.getattr("SIGTERM");
            drop(number.and_then(|number| self.signal.call_method1("signal", (number, previous))));
        }
    }
}

/// Raise [`CommandTerminated`] on SIGTERM while the command runs: only on the main thread, and only when no other handler was installed, so an embedding application keeps its own.
pub(crate) fn handle_sigterm(py: Python<'_>) -> PyResult<TerminationHandler<'_>> {
    let signal: Bound<'_, PyAny> = py.import("signal")?.into_any();
    let threading: Bound<'_, PyAny> = py.import("threading")?.into_any();
    let main_thread: bool = threading
        .call_method0("current_thread")?
        .is(&threading.call_method0("main_thread")?);
    let number: Bound<'_, PyAny> = signal.getattr("SIGTERM")?;
    let current: Bound<'_, PyAny> = signal.call_method1("getsignal", (&number,))?;
    if !main_thread || !current.eq(signal.getattr("SIG_DFL")?)? {
        return Ok(TerminationHandler {
            signal,
            previous: None,
        });
    }
    let handler: Bound<'_, PyCFunction> = PyCFunction::new_closure(
        py,
        None,
        None,
        |_: &Bound<'_, PyTuple>, _: Option<&Bound<'_, PyDict>>| -> PyResult<()> {
            Err(CommandTerminated::new_err(TERMINATED_MESSAGE))
        },
    )?;
    signal.call_method1("signal", (&number, handler))?;
    Ok(TerminationHandler {
        signal,
        previous: Some(current),
    })
}

/// The signal that interrupted the command: SIGTERM for [`CommandTerminated`], SIGINT for any other `KeyboardInterrupt`.
pub(crate) fn interrupting_signal(py: Python<'_>, error: &PyErr) -> Option<i64> {
    if error.is_instance_of::<CommandTerminated>(py) {
        return Some(SIGTERM_NUMBER);
    }
    error
        .is_instance_of::<PyKeyboardInterrupt>(py)
        .then_some(SIGINT_NUMBER)
}

/// Write the termination notice to stderr; a stream that cannot be written changes nothing.
pub(crate) fn report_termination(py: Python<'_>) {
    let written = imported(py, "sys", "stderr").and_then(|stderr| {
        stderr.call_method1("write", (format!("error: {TERMINATED_MESSAGE}\n"),))?;
        stderr.call_method0("flush")
    });
    drop(written);
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add(
        "CommandTerminated",
        module.py().get_type::<CommandTerminated>(),
    )
}
