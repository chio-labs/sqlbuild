//! One transient status line with a spinner on a terminal and plain lines elsewhere.

use std::sync::{Mutex, MutexGuard, PoisonError};

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods};
use pyo3::{pyclass, pymethods};
use sqlbuild_core::cli_text::models::CliStyle;
use sqlbuild_core::progress::main::format_status_spinner_line::format_status_spinner_line;

use crate::bindings::_helpers::build_progress::terminal::{
    CLEAR_LINE, HIDE_CURSOR, SHOW_CURSOR, SPINNER_FRAMES, SPINNER_TICK_SECONDS, claim, flush,
    release, shared_lines, start_spinner, terminal_columns, tty_flag, write,
};
use crate::bindings::_helpers::compile_driver::python_calls::{imported, within};

const SPINNERS_DISABLED_MODULE: &str = "sqlbuild.presentation.main._progress_spinners_disabled";
const PREFLIGHT_COMPLETION_PREFIX: &str = "Prepared ";

/// Mutable reporter state; only held briefly and never across Python calls.
#[derive(Default)]
struct StatusState {
    message: Option<String>,
    active: bool,
    drawn: bool,
    frame: usize,
    stop_event: Option<Py<PyAny>>,
    exit_hook_registered: bool,
}

/// Render one transient status line with optional spinner updates.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct TransientStatusReporter {
    stream: Py<PyAny>,
    lines: Py<PyAny>,
    lock: Py<PyAny>,
    style: CliStyle,
    enabled: bool,
    state: Mutex<StatusState>,
}

impl TransientStatusReporter {
    fn state(&self) -> MutexGuard<'_, StatusState> {
        self.state.lock().unwrap_or_else(PoisonError::into_inner)
    }

    fn locked<T>(&self, py: Python<'_>, body: impl FnOnce() -> PyResult<T>) -> PyResult<T> {
        within(self.lock.bind(py), |_| body())
    }

    fn write_persistent(&self, py: Python<'_>, text: &str) -> PyResult<()> {
        let options: Bound<'_, PyDict> = PyDict::new(py);
        options.set_item("stream", self.stream.bind(py))?;
        options.set_item("text", text)?;
        self.lines
            .bind(py)
            .call_method("write_persistent", (), Some(&options))?;
        Ok(())
    }

    fn write_message(&self, py: Python<'_>, message: &str, dim_output: bool) -> PyResult<()> {
        let formatted: String = if dim_output {
            self.style.muted(message)
        } else {
            message.to_owned()
        };
        self.write_persistent(py, &format!("{formatted}\n"))
    }

    fn draw(&self, py: Python<'_>) -> PyResult<()> {
        let (message, frame) = {
            let mut state = self.state();
            let Some(message) = state.message.clone().filter(|_| state.drawn) else {
                return Ok(());
            };
            let frame: usize = state.frame;
            state.frame = (frame + 1) % SPINNER_FRAMES.len();
            (message, frame)
        };
        let line: String = format_status_spinner_line(
            SPINNER_FRAMES[frame],
            &message,
            terminal_columns(py)?,
            self.style,
        );
        let stream: &Bound<'_, PyAny> = self.stream.bind(py);
        write(stream, &format!("{CLEAR_LINE}{line}"))?;
        flush(stream)
    }

    fn enter_status(slf: &Bound<'_, Self>) -> PyResult<()> {
        let py: Python<'_> = slf.py();
        let reporter: &Self = slf.get();
        let register_hook: bool =
            !std::mem::replace(&mut reporter.state().exit_hook_registered, true);
        if register_hook {
            imported(py, "atexit", "register")?.call1((slf.getattr("close")?,))?;
        }
        let stream: &Bound<'_, PyAny> = reporter.stream.bind(py);
        write(stream, HIDE_CURSOR)?;
        reporter.state().drawn = true;
        reporter.draw(py)?;
        let (event, _thread) = start_spinner(slf.as_any())?;
        reporter.state().stop_event = Some(event.unbind());
        Ok(())
    }

    fn exit_status(&self, py: Python<'_>) -> PyResult<()> {
        let (drawn, event) = {
            let mut state = self.state();
            (std::mem::take(&mut state.drawn), state.stop_event.take())
        };
        if let Some(event) = event {
            event.bind(py).call_method0("set")?;
        }
        if drawn {
            let stream: &Bound<'_, PyAny> = self.stream.bind(py);
            write(stream, &format!("{CLEAR_LINE}{SHOW_CURSOR}"))?;
            flush(stream)?;
        }
        Ok(())
    }
}

#[pymethods]
impl TransientStatusReporter {
    #[new]
    #[pyo3(signature = (*, stream, use_color = false, enabled = true))]
    fn new(
        py: Python<'_>,
        stream: &Bound<'_, PyAny>,
        use_color: bool,
        enabled: bool,
    ) -> PyResult<Self> {
        let lines: Bound<'_, PyAny> = shared_lines(py)?;
        let spinners_disabled: bool =
            imported(py, SPINNERS_DISABLED_MODULE, "progress_spinners_disabled")?
                .call0()?
                .is_truthy()?;
        Ok(Self {
            enabled: enabled && !spinners_disabled && tty_flag(stream)?,
            stream: stream.clone().unbind(),
            lock: lines.getattr("lock")?.unbind(),
            lines: lines.unbind(),
            style: CliStyle { use_color },
            state: Mutex::new(StatusState::default()),
        })
    }

    fn start(slf: &Bound<'_, Self>, message: String) -> PyResult<()> {
        let py: Python<'_> = slf.py();
        let reporter: &Self = slf.get();
        if reporter.enabled {
            return reporter.locked(py, || {
                Self::close(slf)?;
                reporter.state().message = Some(message);
                Self::enter_status(slf)?;
                claim(
                    reporter.lines.bind(py),
                    reporter.stream.bind(py),
                    slf.as_any(),
                )?;
                reporter.state().active = true;
                Ok(())
            });
        }
        reporter.state().active = true;
        reporter.write_message(py, &message, true)
    }

    fn update(&self, py: Python<'_>, message: String) -> PyResult<()> {
        if self.enabled {
            let updated: bool = self.locked(py, || {
                let drawn: bool = {
                    let mut state = self.state();
                    if state.message.is_none() {
                        return Ok(false);
                    }
                    state.message = Some(message.clone());
                    state.drawn
                };
                if drawn {
                    self.draw(py)?;
                }
                Ok(true)
            })?;
            if updated {
                return Ok(());
            }
        }
        self.write_message(py, &message, true)
    }

    #[pyo3(signature = (*, message, blank_line_after = false))]
    fn complete(slf: &Bound<'_, Self>, message: &str, blank_line_after: bool) -> PyResult<()> {
        let py: Python<'_> = slf.py();
        Self::close(slf)?;
        slf.get().write_message(py, message, true)?;
        if blank_line_after {
            slf.get().write_blank_line(py)?;
        }
        Ok(())
    }

    /// Complete with a pre-styled message written verbatim.
    #[pyo3(signature = (*, message, blank_line_after = false))]
    fn complete_styled(
        slf: &Bound<'_, Self>,
        message: &str,
        blank_line_after: bool,
    ) -> PyResult<()> {
        Self::close(slf)?;
        let blank: &str = if blank_line_after { "\n" } else { "" };
        slf.get()
            .write_persistent(slf.py(), &format!("{message}\n{blank}"))
    }

    fn error(slf: &Bound<'_, Self>, message: &str) -> PyResult<()> {
        Self::close(slf)?;
        slf.get().write_message(slf.py(), message, false)
    }

    fn close(slf: &Bound<'_, Self>) -> PyResult<()> {
        let py: Python<'_> = slf.py();
        let reporter: &Self = slf.get();
        reporter.locked(py, || {
            release(reporter.lines.bind(py), slf.as_any())?;
            reporter.exit_status(py)?;
            let mut state = reporter.state();
            state.message = None;
            state.active = false;
            Ok(())
        })
    }

    /// Erase the live status so a persistent line can be written in its place.
    fn clear_transient_line(&self, py: Python<'_>) -> PyResult<()> {
        self.exit_status(py)
    }

    /// Restart the live status below persistent output written while it was active.
    fn redraw_transient_line(slf: &Bound<'_, Self>) -> PyResult<()> {
        let redraw: bool = {
            let state = slf.get().state();
            state.message.is_some() && !state.drawn
        };
        if redraw {
            Self::enter_status(slf)?;
        }
        Ok(())
    }

    /// Render one preflight progress update.
    fn report_preflight_progress(slf: &Bound<'_, Self>, message: String) -> PyResult<()> {
        if message.starts_with(PREFLIGHT_COMPLETION_PREFIX) {
            return Self::complete(slf, &message, true);
        }
        if !slf.get().state().active {
            return Self::start(slf, message);
        }
        slf.get().update(slf.py(), message)
    }

    fn write_blank_line(&self, py: Python<'_>) -> PyResult<()> {
        self.write_persistent(py, "\n")
    }

    fn _spin_until_stopped(&self, py: Python<'_>, stop_event: &Bound<'_, PyAny>) -> PyResult<()> {
        while !stop_event
            .call_method1("wait", (SPINNER_TICK_SECONDS,))?
            .is_truthy()?
        {
            self.locked(py, || {
                if stop_event.call_method0("is_set")?.is_truthy()? {
                    return Ok(());
                }
                self.draw(py)
            })?;
        }
        Ok(())
    }
}

/// A native status reporter writing to `stream`.
pub(crate) fn status_reporter<'py>(
    stream: &Bound<'py, PyAny>,
    use_color: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let reporter: TransientStatusReporter =
        TransientStatusReporter::new(stream.py(), stream, use_color, true)?;
    Ok(Bound::new(stream.py(), reporter)?.into_any())
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<TransientStatusReporter>()
}
