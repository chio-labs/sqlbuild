//! Streamed janitor phase and action lines, as the executor's progress callbacks.

use std::sync::{Mutex, MutexGuard, PoisonError};
use std::time::Instant;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods};
use pyo3::{pyclass, pymethods};
use sqlbuild_core::cli_text::models::CliStyle;
use sqlbuild_core::janitor_text::main::janitor_phase_complete_text::janitor_phase_complete_text;
use sqlbuild_core::janitor_text::main::janitor_phase_failed_text::janitor_phase_failed_text;
use sqlbuild_core::janitor_text::main::janitor_phase_flow_width::janitor_phase_flow_width;
use sqlbuild_core::janitor_text::main::janitor_phase_start_text::janitor_phase_start_text;
use sqlbuild_core::janitor_text::main::render_janitor_item_line::render_janitor_item_line;
use sqlbuild_core::janitor_text::models::{JanitorItemText, JanitorPhase, JanitorPlanText};

use crate::bindings::_helpers::build_progress::terminal::{shared_lines, tty_flag};
use crate::bindings::_helpers::build_progress::transient_status::{
    progress_spinners_disabled, status_reporter,
};
use crate::bindings::_helpers::records::fields::field as native_field;

/// The running phase's start text, size, finished count, column width and start time.
struct ActivePhase {
    message: String,
    total: usize,
    finished: usize,
    flow_width: usize,
    started: Instant,
}

#[derive(Default)]
struct ProgressState {
    items: Vec<JanitorItemText>,
    active: Option<ActivePhase>,
}

/// Print each janitor phase and action as it finishes, and keep the finished actions.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct JanitorProgressPrinter {
    stream: Py<PyAny>,
    status: Py<PyAny>,
    style: CliStyle,
    live: bool,
    plan: JanitorPlanText,
    state: Mutex<ProgressState>,
}

impl JanitorProgressPrinter {
    pub(crate) fn new(
        stream: &Bound<'_, PyAny>,
        style: CliStyle,
        plan: JanitorPlanText,
    ) -> PyResult<Self> {
        Ok(Self {
            stream: stream.clone().unbind(),
            status: status_reporter(stream, style.use_color)?.unbind(),
            style,
            live: tty_flag(stream)? && !progress_spinners_disabled(),
            plan,
            state: Mutex::new(ProgressState::default()),
        })
    }

    fn state(&self) -> MutexGuard<'_, ProgressState> {
        self.state.lock().unwrap_or_else(PoisonError::into_inner)
    }

    /// Every action finished so far, in order.
    pub(crate) fn items(&self) -> Vec<JanitorItemText> {
        self.state().items.clone()
    }

    fn write_persistent(&self, py: Python<'_>, text: &str) -> PyResult<()> {
        let options: Bound<'_, PyDict> = PyDict::new(py);
        options.set_item("stream", self.stream.bind(py))?;
        options.set_item("text", text)?;
        shared_lines(py)?.call_method("write_persistent", (), Some(&options))?;
        Ok(())
    }
}

fn phase(value: &str) -> PyResult<JanitorPhase> {
    JanitorPhase::from_value(value)
        .ok_or_else(|| PyValueError::new_err(format!("unknown janitor phase: {value}")))
}

#[pymethods]
impl JanitorProgressPrinter {
    #[pyo3(signature = (*, phase, total))]
    fn phase_started(&self, py: Python<'_>, phase: &str, total: usize) -> PyResult<()> {
        let phase: JanitorPhase = self::phase(phase)?;
        let message: String = janitor_phase_start_text(phase, total);
        self.state().active = Some(ActivePhase {
            message: message.clone(),
            total,
            finished: 0,
            flow_width: janitor_phase_flow_width(&self.plan, phase),
            started: Instant::now(),
        });
        self.status.bind(py).call_method1("start", (message,))?;
        Ok(())
    }

    /// Record and print one finished action; `item` is its `JanitorProgressItem`.
    #[pyo3(signature = (*, phase, item, error, duration_seconds))]
    fn item_finished(
        &self,
        py: Python<'_>,
        phase: &str,
        item: &Bound<'_, PyAny>,
        error: Option<String>,
        duration_seconds: f64,
    ) -> PyResult<()> {
        let item: JanitorItemText = JanitorItemText {
            phase: self::phase(phase)?,
            action: native_field(item, "action")?.str()?.extract()?,
            name: native_field(item, "name")?.extract()?,
            destination: native_field(item, "destination")?.extract()?,
            error,
            duration_seconds: Some(duration_seconds),
        };
        let (line, progress) = {
            let mut state = self.state();
            let (index, total, width, message) = match state.active.as_mut() {
                Some(active) => {
                    active.finished += 1;
                    (
                        active.finished,
                        active.total,
                        active.flow_width,
                        active.message.clone(),
                    )
                }
                None => (1, 1, 0, String::new()),
            };
            let line: String = render_janitor_item_line((index, total), &item, width, self.style);
            state.items.push(item);
            (line, format!("{message} {index}/{total}"))
        };
        self.write_persistent(py, &format!("{line}\n"))?;
        if self.live {
            self.status.bind(py).call_method1("update", (progress,))?;
        }
        Ok(())
    }

    #[pyo3(signature = (*, phase, failed))]
    fn phase_finished(&self, py: Python<'_>, phase: &str, failed: bool) -> PyResult<()> {
        let phase: JanitorPhase = self::phase(phase)?;
        let (active, items) = {
            let mut state = self.state();
            (state.active.take(), state.items.clone())
        };
        let (total, elapsed) = active.as_ref().map_or((0, 0.0), |active| {
            (active.total, active.started.elapsed().as_secs_f64())
        });
        let options: Bound<'_, PyDict> = PyDict::new(py);
        if failed {
            let completed: usize = items
                .iter()
                .filter(|item| item.phase == phase && item.error.is_none())
                .count();
            options.set_item(
                "message",
                janitor_phase_failed_text(phase, (completed, total), elapsed, self.style),
            )?;
            self.status
                .bind(py)
                .call_method("complete_styled", (), Some(&options))?;
            return Ok(());
        }
        options.set_item(
            "message",
            janitor_phase_complete_text(phase, &items, elapsed),
        )?;
        self.status
            .bind(py)
            .call_method("complete", (), Some(&options))?;
        Ok(())
    }
}
