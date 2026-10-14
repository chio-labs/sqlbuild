//! Terminal width, the shared transient line coordinator and spinner threads of progress reporters.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyTuple};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};

const COLUMNS_MODULE: &str = "sqlbuild.presentation.main.terminal_columns";
const LINES_MODULE: &str = "sqlbuild.presentation.main.transient_line_coordinator";
const SPINNER_JOIN_SECONDS: f64 = 0.2;
pub(crate) const SPINNER_TICK_SECONDS: f64 = 0.1;
pub(crate) const CLEAR_LINE: &str = "\r\u{1b}[K";
pub(crate) const HIDE_CURSOR: &str = "\u{1b}[?25l";
pub(crate) const SHOW_CURSOR: &str = "\u{1b}[?25h";
pub(crate) const SPINNER_FRAMES: [&str; 10] = [
    "\u{280b}", "\u{2819}", "\u{2839}", "\u{2838}", "\u{283c}", "\u{2834}", "\u{2826}", "\u{2827}",
    "\u{2807}", "\u{280f}",
];

/// The current terminal width.
pub(crate) fn terminal_columns(py: Python<'_>) -> PyResult<usize> {
    let columns: i64 = imported(py, COLUMNS_MODULE, "terminal_columns")?
        .call0()?
        .extract()?;
    Ok(usize::try_from(columns).unwrap_or(0))
}

/// The process-wide coordinator of the one live transient line.
pub(crate) fn shared_lines(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    imported(py, LINES_MODULE, "shared_transient_line_coordinator")?.call0()
}

/// Whether `stream` reports a terminal.
pub(crate) fn tty_flag(stream: &Bound<'_, PyAny>) -> PyResult<bool> {
    if !stream.hasattr("isatty")? {
        return Ok(false);
    }
    stream.call_method0("isatty")?.is_truthy()
}

/// The current native progress projector, if a projection is active.
pub(crate) fn projector(py: Python<'_>) -> PyResult<Option<Py<PyAny>>> {
    let projector: Bound<'_, PyAny> =
        imported(py, "sqlbuild._native", "current_native_progress_projector")?.call0()?;
    Ok((!projector.is_none()).then(|| projector.unbind()))
}

/// The projector's canonical duration of a finished resource, `None` while it is pending.
pub(crate) fn consume_terminal(
    projector: &Bound<'_, PyAny>,
    resource_name: &str,
    resource_id: Option<&str>,
) -> PyResult<Option<f64>> {
    let options: Bound<'_, PyDict> = PyDict::new(projector.py());
    options.set_item("resource_name", resource_name)?;
    options.set_item("resource_id", resource_id)?;
    projector
        .call_method("consume_resource_terminal", (), Some(&options))?
        .extract()
}

/// Claim or release the live line for `owner`.
pub(crate) fn claim(
    lines: &Bound<'_, PyAny>,
    stream: &Bound<'_, PyAny>,
    owner: &Bound<'_, PyAny>,
) -> PyResult<()> {
    let options: Bound<'_, PyDict> = PyDict::new(lines.py());
    options.set_item("stream", stream)?;
    options.set_item("owner", owner)?;
    lines.call_method("claim", (), Some(&options))?;
    Ok(())
}

pub(crate) fn release(lines: &Bound<'_, PyAny>, owner: &Bound<'_, PyAny>) -> PyResult<()> {
    let options: Bound<'_, PyDict> = PyDict::new(lines.py());
    options.set_item("owner", owner)?;
    lines.call_method("release", (), Some(&options))?;
    Ok(())
}

pub(crate) fn write(stream: &Bound<'_, PyAny>, text: &str) -> PyResult<()> {
    stream.call_method1("write", (text,))?;
    Ok(())
}

pub(crate) fn flush(stream: &Bound<'_, PyAny>) -> PyResult<()> {
    stream.call_method0("flush")?;
    Ok(())
}

/// Start a daemon thread running `owner._spin_until_stopped(event)`; return the event and thread.
pub(crate) fn start_spinner<'py>(
    owner: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let py: Python<'py> = owner.py();
    let event: Bound<'py, PyAny> = imported(py, "threading", "Event")?.call0()?;
    let thread: Bound<'py, PyAny> = call_with(
        &imported(py, "threading", "Thread")?,
        &[
            ("target", owner.getattr("_spin_until_stopped")?),
            ("args", PyTuple::new(py, [&event])?.into_any()),
            ("daemon", PyBool::new(py, true).to_owned().into_any()),
        ],
    )?;
    thread.call_method0("start")?;
    Ok((event, thread))
}

/// Join a stopped spinner thread briefly if it is still alive.
pub(crate) fn join_spinner(thread: &Bound<'_, PyAny>) -> PyResult<()> {
    if thread.call_method0("is_alive")?.is_truthy()? {
        let options: Bound<'_, PyDict> = PyDict::new(thread.py());
        options.set_item("timeout", SPINNER_JOIN_SECONDS)?;
        thread.call_method("join", (), Some(&options))?;
    }
    Ok(())
}
