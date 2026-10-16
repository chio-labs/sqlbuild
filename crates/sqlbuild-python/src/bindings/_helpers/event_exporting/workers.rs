//! The dispatcher's delivery, notification, health and per-invocation thread targets.

use std::sync::{Arc, Mutex};
use std::time::Instant;

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyErr, PyResult, Python, pyclass, pymethods};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyString};
use sqlbuild_core::event_export::constants::TIMEOUT_ERROR_TYPE;
use sqlbuild_core::event_export::main::drop_lifecycle_attempts::drop_lifecycle_attempts;
use sqlbuild_core::event_export::main::take_lifecycle_event::take_lifecycle_event;
use sqlbuild_core::event_export::models::{EventQueue, ExportSnapshot, QueuedEvent};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::event_exporting::constants::{
    INVOCATION_THREAD_PREFIX, NO_SECONDS, POLL_SECONDS,
};
use crate::bindings::_helpers::event_exporting::dispatcher::{Exporter, Queued, Shared};
use crate::bindings::_helpers::event_exporting::models::{
    EventExportSummary, EventExporterFailure,
};
use crate::bindings::_helpers::event_exporting::values::error_type_of;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::native_host::user_code::UserCodeHost;
use crate::bindings::_helpers::native_threads::exit_signal::interpreter_exiting;

/// Which long-lived dispatcher thread a worker runs.
#[derive(Clone, Copy)]
pub(crate) enum WorkerRole {
    Dispatch,
    Notify,
    Health,
}

/// A long-lived dispatcher thread's target.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct DispatcherWorker {
    shared: Arc<Shared>,
    role: WorkerRole,
}

/// Whether an invocation finished, and the sanitized type of what it raised.
#[derive(Default)]
struct Completion {
    done: bool,
    error_type: Option<String>,
}

/// Reports how one sink call on its own daemon thread ended.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct InvocationCompletion {
    shared: Arc<Shared>,
    invocation: u64,
    completion: Arc<Mutex<Completion>>,
}

/// The next thing the notification thread delivers.
enum Notification {
    Periodic(ExportSnapshot),
    Final(Py<EventExportSummary>),
    Failure(EventExporterFailure),
    Stop,
}

/// Whether the call finished, and the sanitized type of what it raised.
fn completion_state(completion: &Mutex<Completion>) -> PyResult<(bool, Option<String>)> {
    let completion = completion
        .lock()
        .map_err(|_| PyRuntimeError::new_err("event exporter invocation lock is poisoned"))?;
    Ok((completion.done, completion.error_type.clone()))
}

impl DispatcherWorker {
    pub(crate) fn new(shared: Arc<Shared>, role: WorkerRole) -> Self {
        Self { shared, role }
    }

    /// The state this worker's dispatcher shares.
    pub(crate) fn shared(&self) -> &Shared {
        &self.shared
    }

    /// Wait until bound, returning `false` when stopped first.
    fn await_bound(&self, py: Python<'_>) -> PyResult<bool> {
        let shared = &self.shared;
        let _held = shared.hold(py)?;
        loop {
            let state = shared.locked()?;
            if state.bound {
                return Ok(true);
            }
            if state.stopping || state.force_stop {
                return Ok(false);
            }
            drop(state);
            shared.wait(py, POLL_SECONDS)?;
        }
    }

    /// The next queued event, `Ok(None)` to keep polling and `Err(())` once delivery stops.
    fn next_event(&self, py: Python<'_>) -> PyResult<Result<Option<QueuedEvent<Queued>>, ()>> {
        let shared = &self.shared;
        let _held = shared.hold(py)?;
        let mut state = shared.locked()?;
        if Shared::past_deadline(&state) || state.force_stop {
            let drained: Vec<QueuedEvent<Queued>> = std::mem::take(&mut state.queue.items);
            for item in &drained {
                state.counts = drop_lifecycle_attempts(
                    std::mem::take(&mut state.counts),
                    &item.eligible_exporters,
                );
            }
            drop(state);
            drop(drained);
            return Ok(Err(()));
        }
        if state.queue.items.is_empty() {
            drop(state);
            shared.wait(py, POLL_SECONDS)?;
            state = shared.locked()?;
        }
        let capacity: usize = state.queue.capacity;
        let (queue, next) = take_lifecycle_event(std::mem::replace(
            &mut state.queue,
            EventQueue::new(capacity),
        ));
        state.queue = queue;
        match next {
            Some(item) => Ok(Ok(Some(item))),
            None if state.stopping => Ok(Err(())),
            None => Ok(Ok(None)),
        }
    }

    fn run_dispatch(&self, py: Python<'_>) -> PyResult<()> {
        let result = (|| -> PyResult<()> {
            if !self.await_bound(py)? {
                return Ok(());
            }
            while let Ok(item) = self.next_event(py)? {
                if let Some(item) = item {
                    self.deliver(py, &item)?;
                }
            }
            Ok(())
        })();
        self.shared.dispatcher_finished(py)?;
        result
    }

    /// Offer one event to each eligible exporter in order, before the drain deadline.
    fn deliver(&self, py: Python<'_>, item: &QueuedEvent<Queued>) -> PyResult<()> {
        let shared = &self.shared;
        for (position, index) in item.eligible_exporters.iter().enumerate() {
            let exporter: Arc<Exporter> = {
                let _held = shared.hold(py)?;
                let mut state = shared.locked()?;
                if Shared::past_deadline(&state) {
                    state.counts = drop_lifecycle_attempts(
                        std::mem::take(&mut state.counts),
                        &item.eligible_exporters[position..],
                    );
                    return Ok(());
                }
                if state.blocked.contains(index) {
                    state.counts =
                        drop_lifecycle_attempts(std::mem::take(&mut state.counts), &[*index]);
                    continue;
                }
                let Some(exporter) = state.exporters.get(*index) else {
                    continue;
                };
                Arc::clone(exporter)
            };
            self.invoke(py, (*index, exporter), item)?;
        }
        Ok(())
    }

    /// Call one exporter on its own daemon thread and account for its outcome.
    fn invoke(
        &self,
        py: Python<'_>,
        (index, exporter): (usize, Arc<Exporter>),
        item: &QueuedEvent<Queued>,
    ) -> PyResult<()> {
        let shared = &self.shared;
        let failure = (index, item.item.kind.as_str(), item.item.severity);
        let completion: Arc<Mutex<Completion>> = Arc::new(Mutex::new(Completion::default()));
        let name: String = format!("{INVOCATION_THREAD_PREFIX}{}", exporter.name);
        let invocation: u64 = shared.begin_invocation(py)?;
        let reporter = InvocationCompletion::new(Arc::clone(shared), invocation, &completion);
        let started = Py::new(py, reporter).and_then(|reporter| {
            let arguments = PyDict::new(py);
            arguments.set_item("function", exporter.function.bind(py))?;
            arguments.set_item("provider_arguments", exporter.provider_arguments.bind(py))?;
            arguments.set_item("event", item.item.event.bind(py))?;
            arguments.set_item("completion", reporter)?;
            let thread = call_with(
                &imported(py, "threading", "Thread")?,
                &[
                    (
                        "target",
                        host::entry(py, UserCodeHost::InvokeLifecycleEventSink)?,
                    ),
                    ("kwargs", arguments.into_any()),
                    ("name", PyString::new(py, &name).into_any()),
                    ("daemon", PyBool::new(py, true).to_owned().into_any()),
                ],
            )?;
            thread.call_method0("start")
        });
        if let Err(error) = started {
            shared.invocation_finished(py, invocation)?;
            return shared.record_failure(py, failure, error_type_of(py, &error));
        }
        let completed: bool = self.await_invocation(py, &completion)?;
        let (_, error_type) = completion_state(&completion)?;
        if !completed {
            {
                let _held = shared.hold(py)?;
                shared.locked()?.blocked.insert(index);
            }
            return shared.record_failure(py, failure, TIMEOUT_ERROR_TYPE.to_owned());
        }
        if let Some(error_type) = error_type {
            return shared.record_failure(py, failure, error_type);
        }
        let _held = shared.hold(py)?;
        if let Some(counts) = shared.locked()?.counts.get_mut(index) {
            counts.delivered += 1;
        }
        Ok(())
    }

    /// Wait for an invocation until its own timeout or the drain deadline, whichever is first.
    fn await_invocation(&self, py: Python<'_>, completion: &Mutex<Completion>) -> PyResult<bool> {
        let shared = &self.shared;
        let invocation_deadline: Instant = Instant::now() + shared.invocation_timeout;
        let _held = shared.hold(py)?;
        loop {
            let state = shared.locked()?;
            let effective: Instant = state.deadline.map_or(invocation_deadline, |deadline| {
                deadline.min(invocation_deadline)
            });
            let force_stop: bool = state.force_stop || interpreter_exiting(py)?;
            drop(state);
            let remaining: f64 = effective
                .saturating_duration_since(Instant::now())
                .as_secs_f64();
            if remaining <= NO_SECONDS || force_stop {
                return Ok(completion_state(completion)?.0);
            }
            shared.wait(py, remaining.min(POLL_SECONDS))?;
            if completion_state(completion)?.0 {
                return Ok(true);
            }
        }
    }

    fn next_notification(&self, py: Python<'_>) -> PyResult<Notification> {
        let shared = &self.shared;
        let _held = shared.hold(py)?;
        loop {
            let mut state = shared.locked()?;
            if let Some(snapshot) = state.pending_periodic.take() {
                state.periodic_inflight = Some(snapshot.health_signature());
                return Ok(Notification::Periodic(snapshot));
            }
            state.periodic_inflight = None;
            if !state.final_delivered
                && let Some(summary) = &state.final_notification
            {
                return Ok(Notification::Final(summary.clone_ref(py)));
            }
            if let Some(failure) = state.failures.pop_front() {
                return Ok(Notification::Failure(failure));
            }
            if state.notification_stopping {
                return Ok(Notification::Stop);
            }
            drop(state);
            shared.wait(py, POLL_SECONDS)?;
        }
    }

    fn run_notifications(&self, py: Python<'_>) -> PyResult<()> {
        let shared = &self.shared;
        loop {
            match self.next_notification(py)? {
                Notification::Periodic(snapshot) => {
                    let signature: [u64; 7] = snapshot.health_signature();
                    if let Some(callback) = &shared.summary_callback {
                        let summary = EventExportSummary::object(py, snapshot)?;
                        drop(callback.bind(py).call1((summary,)));
                    }
                    let _held = shared.hold(py)?;
                    let mut state = shared.locked()?;
                    state.last_published_periodic = signature;
                    state.periodic_inflight = None;
                }
                Notification::Final(summary) => {
                    if let Some(callback) = &shared.summary_callback {
                        drop(callback.bind(py).call1((summary,)));
                    }
                    let released = {
                        let _held = shared.hold(py)?;
                        let mut state = shared.locked()?;
                        state.final_delivered = true;
                        state.final_notification.take()
                    };
                    drop(released);
                    return Ok(());
                }
                Notification::Failure(failure) => {
                    if let Some(callback) = &shared.failure_callback {
                        let failure = Py::new(py, failure)?;
                        drop(callback.bind(py).call1((failure,)));
                    }
                }
                Notification::Stop => return Ok(()),
            }
        }
    }

    /// Wait one health interval, returning `false` once health publication stops.
    fn await_interval(&self, py: Python<'_>) -> PyResult<bool> {
        let shared = &self.shared;
        let deadline: Instant = Instant::now() + shared.health_interval;
        let _held = shared.hold(py)?;
        loop {
            if shared.locked()?.health_stopping {
                return Ok(false);
            }
            let remaining: f64 = deadline
                .saturating_duration_since(Instant::now())
                .as_secs_f64();
            if remaining <= NO_SECONDS {
                return Ok(true);
            }
            shared.wait(py, remaining)?;
        }
    }

    fn run_health(&self, py: Python<'_>) -> PyResult<()> {
        let shared = &self.shared;
        while self.await_interval(py)? {
            let snapshot: ExportSnapshot = shared.current_snapshot(py)?;
            let signature: [u64; 7] = snapshot.health_signature();
            let _held = shared.hold(py)?;
            let mut state = shared.locked()?;
            if state.health_stopping || state.final_notification.is_some() {
                return Ok(());
            }
            if signature == state.last_published_periodic
                || state.periodic_inflight == Some(signature)
            {
                state.pending_periodic = None;
                continue;
            }
            state.pending_periodic = Some(snapshot);
            drop(state);
            shared.notify_all(py)?;
        }
        Ok(())
    }
}

#[pymethods]
impl DispatcherWorker {
    fn __call__(&self, py: Python<'_>) -> PyResult<()> {
        match self.role {
            WorkerRole::Dispatch => self.run_dispatch(py),
            WorkerRole::Notify => self.run_notifications(py),
            WorkerRole::Health => self.run_health(py),
        }
    }
}

impl InvocationCompletion {
    /// A reporter that records into `completion` and ends `invocation`.
    fn new(shared: Arc<Shared>, invocation: u64, completion: &Arc<Mutex<Completion>>) -> Self {
        Self {
            shared,
            invocation,
            completion: Arc::clone(completion),
        }
    }
}

#[pymethods]
impl InvocationCompletion {
    #[pyo3(signature = (error, /))]
    fn __call__(&self, py: Python<'_>, error: Option<&Bound<'_, PyAny>>) -> PyResult<()> {
        if let Some(error) = error {
            let error_type: String = error_type_of(py, &PyErr::from_value(error.clone()));
            if let Ok(mut completion) = self.completion.lock() {
                completion.error_type = Some(error_type);
            }
        }
        let finished = self.shared.invocation_finished(py, self.invocation);
        let _held = self.shared.hold(py)?;
        if let Ok(mut completion) = self.completion.lock() {
            completion.done = true;
        }
        self.shared.notify_all(py)?;
        finished
    }
}
