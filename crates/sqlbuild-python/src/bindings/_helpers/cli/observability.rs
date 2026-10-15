//! The observed CLI invocation: lifecycle dispatcher, native progress, terminal index and sinks.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Mutex, MutexGuard};

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::{
    Bound, Py, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyBool, PyString, PyTuple, PyTupleMethods};
use pyo3::{IntoPyObjectExt, pyclass, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_cli::dispatch::main::event_export_warning::event_export_warning;
use sqlbuild_cli::dispatch::models::{ExportSummary, ExporterLoss};
use sqlbuild_core::event_export::constants::DEFAULT_EVENT_EXPORT_SHUTDOWN_TIMEOUT_SECONDS;

use crate::bindings::_helpers::cli::launch_state::withhold_launch_record;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::presentation_text::terminal::stdout_supports_color;

const NATIVE_MODULE: &str = "sqlbuild._native";
const EVENT_DISPATCHER_MODULE: &str = "sqlbuild.runtime.observability.classes.event_dispatcher";
const DISPATCHER_SCOPE_MODULE: &str = "sqlbuild.runtime.observability.main.dispatcher_scope";
const IDENTITY_MODULE: &str = "sqlbuild.runtime.observability.main.current_execution_identity";
const EXTENSIONS_MODULE: &str = "sqlbuild.compiler.discovery.main.runtime_extensions";
const OUTPUT_CAPTURE_MODULE: &str =
    "sqlbuild.runtime.output_capture.main.configured_output_capture_scope";
const DEBUG_EVENT_MODULE: &str = "sqlbuild.diagnostics.main.log_debug_event";
const OBSERVABILITY_LOGGER: &str = "sqlbuild.cli.observability";
const DEBUG_COMMAND: &str = "debug";
const LINEAGE_COMMAND: &str = "lineage";
const INVOCATION_COMPLETED: &str = "invocation_completed";
const INVOCATION_FAILED: &str = "invocation_failed";
const SUMMARY_FIELDS: [&str; 3] = ["queue_depth", "queue_capacity", "flush_complete"];
const COUNT_FIELDS: [&str; 5] = ["accepted", "filtered", "delivered", "failed", "dropped"];

/// `log_debug_event(logger=<observability logger>, message=message, **fields)`.
fn log_debug<'py>(
    py: Python<'py>,
    message: &str,
    fields: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<()> {
    let logger: Bound<'py, PyAny> =
        imported(py, "logging", "getLogger")?.call1((OBSERVABILITY_LOGGER,))?;
    let mut pairs: Vec<(&str, Bound<'py, PyAny>)> = vec![
        ("logger", logger),
        ("message", PyString::new(py, message).into_any()),
    ];
    pairs.extend(fields.iter().cloned());
    call_with(
        &imported(py, DEBUG_EVENT_MODULE, "log_debug_event")?,
        &pairs,
    )?;
    Ok(())
}

fn error_type_name<'py>(py: Python<'py>, error: &PyErr) -> PyResult<Bound<'py, PyAny>> {
    error.get_type(py).getattr("__name__")
}

/// Log a failed lifecycle subscriber.
#[pyfunction]
fn log_dispatch_failure(failure: &Bound<'_, PyAny>) -> PyResult<()> {
    log_debug(
        failure.py(),
        "Lifecycle event subscriber failed",
        &[
            ("error_type", failure.getattr("error_type")?),
            ("channel", failure.getattr("channel")?),
            ("subscriber", failure.getattr("subscriber")?),
        ],
    )
}

/// Log a failed event exporter delivery.
#[pyfunction]
fn log_exporter_failure(failure: &Bound<'_, PyAny>) -> PyResult<()> {
    log_debug(
        failure.py(),
        "Event exporter delivery failed",
        &[
            ("exporter_name", failure.getattr("exporter_name")?),
            ("error_type", failure.getattr("error_type")?),
            ("event_kind", failure.getattr("event_kind")?),
            ("event_severity", failure.getattr("event_severity")?),
        ],
    )
}

/// Log a failed command-output sink delivery.
#[pyfunction]
fn log_command_output_failure(error: &Bound<'_, PyAny>) -> PyResult<()> {
    log_debug(
        error.py(),
        "Command-output sink delivery failed",
        &[("error_type", error.get_type().getattr("__name__")?)],
    )
}

/// Log the event exporter delivery summary and each exporter's accounting.
#[pyfunction]
fn log_exporter_summary(summary: &Bound<'_, PyAny>) -> PyResult<()> {
    let py: Python<'_> = summary.py();
    let mut fields: Vec<(&str, Bound<'_, PyAny>)> = Vec::new();
    for name in COUNT_FIELDS.into_iter().chain(SUMMARY_FIELDS) {
        fields.push((name, summary.getattr(name)?));
    }
    log_debug(py, "Event exporter delivery summary", &fields)?;
    for exporter in summary.getattr("per_exporter")?.try_iter()? {
        let exporter: Bound<'_, PyAny> = exporter?;
        let counts: Bound<'_, PyAny> = exporter.getattr("counts")?;
        let mut fields: Vec<(&str, Bound<'_, PyAny>)> =
            vec![("exporter_name", exporter.getattr("exporter_name")?)];
        for name in COUNT_FIELDS {
            fields.push((name, counts.getattr(name)?));
        }
        for name in SUMMARY_FIELDS {
            fields.push((name, summary.getattr(name)?));
        }
        log_debug(py, "Event exporter accounting", &fields)?;
    }
    Ok(())
}

/// Records whether the invocation published a successful terminal fact.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct InvocationOutcome {
    succeeded: AtomicBool,
}

#[pymethods]
impl InvocationOutcome {
    fn consume(&self, event: &Bound<'_, PyAny>) -> PyResult<()> {
        let event_type: String = event.getattr("event_type")?.extract()?;
        if event_type == INVOCATION_COMPLETED || event_type == INVOCATION_FAILED {
            self.succeeded
                .store(event_type == INVOCATION_COMPLETED, Ordering::SeqCst);
        }
        Ok(())
    }
}

/// What an observed invocation installed, released in reverse when it ends.
struct Observed {
    dispatcher: Py<PyAny>,
    projector: Py<PyAny>,
    projector_token: Py<PyAny>,
    unsubscribe_terminal_index: Py<PyAny>,
    unsubscribe_progress: Py<PyAny>,
    outcome: Py<InvocationOutcome>,
    exporter_scope: Option<Py<PyAny>>,
    unsubscribe_exporters: Option<Py<PyAny>>,
    unsubscribe_outcome: Option<Py<PyAny>>,
    /// Context managers entered, innermost last.
    entered: Vec<Py<PyAny>>,
}

/// Log a cleanup failure without letting logging fail the command.
fn report_cleanup_failure(py: Python<'_>, error: &PyErr, phase: &str) {
    let reported = error_type_name(py, error).and_then(|error_type| {
        log_debug(
            py,
            "CLI observability cleanup failed",
            &[
                ("error_type", error_type),
                ("phase", PyString::new(py, phase).into_any()),
            ],
        )
    });
    drop(reported);
}

fn run_cleanup<T>(py: Python<'_>, result: PyResult<T>, phase: &str) {
    if let Err(error) = result {
        report_cleanup_failure(py, &error, phase);
    }
}

/// Native export accounting of a Python `EventExportSummary`.
fn export_summary(summary: &Bound<'_, PyAny>) -> PyResult<ExportSummary> {
    let mut per_exporter: Vec<ExporterLoss> = Vec::new();
    for exporter in summary.getattr("per_exporter")?.try_iter()? {
        let exporter: Bound<'_, PyAny> = exporter?;
        let counts: Bound<'_, PyAny> = exporter.getattr("counts")?;
        per_exporter.push(ExporterLoss {
            exporter_name: exporter.getattr("exporter_name")?.extract()?,
            dropped: counts.getattr("dropped")?.extract()?,
            failed: counts.getattr("failed")?.extract()?,
        });
    }
    Ok(ExportSummary {
        accepted: summary.getattr("accepted")?.extract()?,
        dropped: summary.getattr("dropped")?.extract()?,
        failed: summary.getattr("failed")?.extract()?,
        per_exporter,
    })
}

/// Print the incomplete-export warning to stderr when events were dropped or failed.
fn warn_incomplete_export(summary: &Bound<'_, PyAny>, command_succeeded: bool) -> PyResult<()> {
    let py: Python<'_> = summary.py();
    let Some(message) = event_export_warning(&export_summary(summary)?, command_succeeded) else {
        return Ok(());
    };
    let options = pyo3::types::PyDict::new(py);
    pyo3::types::PyDictMethods::set_item(&options, "file", py.import("sys")?.getattr("stderr")?)?;
    pyo3::types::PyDictMethods::set_item(&options, "flush", true)?;
    py.import("builtins")?
        .getattr("print")?
        .call((message,), Some(&options))?;
    Ok(())
}

impl Observed {
    /// Leave entered contexts innermost first; the exception raised by one, and whether any suppressed.
    fn exit_contexts(
        &mut self,
        py: Python<'_>,
        mut pending: Option<PyErr>,
    ) -> (Option<PyErr>, bool) {
        let mut suppressed: bool = false;
        while let Some(manager) = self.entered.pop() {
            let arguments: (Py<PyAny>, Py<PyAny>, Py<PyAny>) = pending.as_ref().map_or_else(
                || (py.None(), py.None(), py.None()),
                |error| {
                    (
                        error.get_type(py).into_any().unbind(),
                        error.value(py).clone().into_any().unbind(),
                        error
                            .traceback(py)
                            .map_or_else(|| py.None(), |traceback| traceback.into_any().unbind()),
                    )
                },
            );
            match manager.bind(py).call_method1("__exit__", arguments) {
                Ok(result) => {
                    if pending.is_some() && result.is_truthy().unwrap_or(false) {
                        pending = None;
                        suppressed = true;
                    }
                }
                Err(error) => {
                    pending = Some(error);
                    suppressed = false;
                }
            }
        }
        (pending, suppressed)
    }

    /// Release exporters, progress and the terminal index, then warn about lost events.
    fn release(self, py: Python<'_>) {
        if let Some(unsubscribe) = &self.unsubscribe_exporters {
            run_cleanup(
                py,
                unsubscribe.bind(py).call0(),
                "event_exporter_unsubscribe",
            );
        }
        if let Some(unsubscribe) = &self.unsubscribe_outcome {
            run_cleanup(
                py,
                unsubscribe.bind(py).call0(),
                "invocation_outcome_unsubscribe",
            );
        }
        let summary: Option<Bound<'_, PyAny>> = self.exporter_scope.as_ref().and_then(|scope| {
            match scope.bind(py).call_method0("close") {
                Ok(summary) => Some(summary),
                Err(error) => {
                    report_cleanup_failure(py, &error, "event_exporter_shutdown");
                    None
                }
            }
        });
        run_cleanup(
            py,
            self.unsubscribe_terminal_index.bind(py).call0(),
            "terminal_index_unsubscribe",
        );
        run_cleanup(
            py,
            self.unsubscribe_progress.bind(py).call0(),
            "progress_unsubscribe",
        );
        let projector: &Bound<'_, PyAny> = self.projector.bind(py);
        run_cleanup(py, projector.call_method0("close"), "progress_close");
        run_cleanup(
            py,
            projector.call_method1("restore", (&self.projector_token,)),
            "progress_context_restore",
        );
        if let Some(summary) = summary.filter(|summary| !summary.is_none()) {
            let succeeded: bool = self.outcome.get().succeeded.load(Ordering::SeqCst);
            run_cleanup(
                py,
                warn_incomplete_export(&summary, succeeded),
                "event_exporter_warning",
            );
        }
    }

    fn subscribe(&self, py: Python<'_>, subscriber: Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        Ok(call_with(
            &self.dispatcher.bind(py).getattr("subscribe_lifecycle")?,
            &[
                ("subscriber", subscriber),
                (
                    "accepts_opaque",
                    PyBool::new(py, false).to_owned().into_any(),
                ),
            ],
        )?
        .unbind())
    }

    fn enter(&mut self, manager: Bound<'_, PyAny>) -> PyResult<()> {
        manager.call_method0("__enter__")?;
        self.entered.push(manager.unbind());
        Ok(())
    }

    /// Bind configured project event exporters and command-output sinks, then install scopes.
    fn install(
        &mut self,
        py: Python<'_>,
        (args, project_dir): (&Bound<'_, PyAny>, &Bound<'_, PyAny>),
        terminal_index: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let mut command_output_sinks: bool = false;
        if args.getattr("command")?.ne(LINEAGE_COMMAND)? {
            let extensions: Bound<'_, PyAny> = call_with(
                &imported(py, EXTENSIONS_MODULE, "discover_runtime_extensions")?,
                &[("project_dir", project_dir.clone())],
            )?;
            let event_exporters: Bound<'_, PyAny> = extensions.getattr("event_exporters")?;
            let sinks: Bound<'_, PyAny> = extensions.getattr("command_output_sinks")?;
            command_output_sinks = sinks.is_truthy()?;
            if event_exporters.is_truthy()? || command_output_sinks {
                withhold_launch_record(py)?;
                let timeout: Bound<'_, PyAny> =
                    extensions.getattr("lifecycle_shutdown_timeout_seconds")?;
                let timeout: f64 = if timeout.is_none() {
                    DEFAULT_EVENT_EXPORT_SHUTDOWN_TIMEOUT_SECONDS
                } else {
                    timeout.extract::<f64>()?
                };
                let timeout: Bound<'_, PyAny> = timeout.into_bound_py_any(py)?;
                let delivery: Bound<'_, PyAny> = call_with(
                    &imported(py, NATIVE_MODULE, "EventExporterDispatcher")?,
                    &[
                        ("shutdown_timeout_seconds", timeout),
                        (
                            "failure_callback",
                            wrap_pyfunction!(log_exporter_failure, py)?.into_any(),
                        ),
                        (
                            "summary_callback",
                            wrap_pyfunction!(log_exporter_summary, py)?.into_any(),
                        ),
                    ],
                )?;
                let scope: Bound<'_, PyAny> = call_with(
                    &imported(py, NATIVE_MODULE, "EventExporterCommandScope")?,
                    &[("dispatcher", delivery.clone())],
                )?;
                self.exporter_scope = Some(scope.clone().unbind());
                call_with(
                    &scope.getattr("configure_extensions")?,
                    &[
                        ("project_dir", project_dir.clone()),
                        ("providers", extensions.getattr("providers")?),
                        ("event_exporters", event_exporters),
                        ("command_output_sinks", sinks),
                    ],
                )?;
                self.unsubscribe_exporters =
                    Some(self.subscribe(py, delivery.getattr("enqueue")?)?);
                let outcome: Bound<'_, PyAny> = self.outcome.bind(py).clone().into_any();
                self.unsubscribe_outcome = Some(self.subscribe(py, outcome.getattr("consume")?)?);
            }
        }
        self.enter(
            imported(py, DISPATCHER_SCOPE_MODULE, "dispatcher_scope")?
                .call1((self.dispatcher.bind(py),))?,
        )?;
        self.enter(
            imported(py, NATIVE_MODULE, "terminal_event_index_scope")?.call1((terminal_index,))?,
        )?;
        let Some(scope) = self
            .exporter_scope
            .as_ref()
            .map(|scope| scope.bind(py).clone())
        else {
            return Ok(());
        };
        self.enter(imported(py, NATIVE_MODULE, "event_exporter_command_scope")?.call1((&scope,))?)?;
        let identity: Bound<'_, PyAny> =
            imported(py, IDENTITY_MODULE, "current_execution_identity")?.call0()?;
        if !identity.is_none() && command_output_sinks {
            self.enter(call_with(
                &imported(py, OUTPUT_CAPTURE_MODULE, "configured_output_capture_scope")?,
                &[
                    ("exporter_scope", scope),
                    ("identity", identity),
                    (
                        "failure_callback",
                        wrap_pyfunction!(log_command_output_failure, py)?.into_any(),
                    ),
                ],
            )?)?;
        }
        Ok(())
    }
}

/// Installs native progress, terminal indexing and configured event exporters for one command.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct CliObservabilityScope {
    args: Py<PyAny>,
    project_dir: Py<PyAny>,
    observed: Mutex<Option<Observed>>,
}

impl CliObservabilityScope {
    fn locked(&self) -> PyResult<MutexGuard<'_, Option<Observed>>> {
        self.observed
            .lock()
            .map_err(|_| PyRuntimeError::new_err("observability scope lock is poisoned"))
    }
}

#[pymethods]
impl CliObservabilityScope {
    fn __enter__(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let args: &Bound<'_, PyAny> = self.args.bind(py);
        let dispatcher: Bound<'_, PyAny> = call_with(
            &imported(py, EVENT_DISPATCHER_MODULE, "EventDispatcher")?,
            &[(
                "health_callback",
                wrap_pyfunction!(log_dispatch_failure, py)?.into_any(),
            )],
        )?;
        let terminal_index: Bound<'_, PyAny> =
            imported(py, NATIVE_MODULE, "TerminalEventIndex")?.call0()?;
        let subscribe = |subscriber: Bound<'_, PyAny>| -> PyResult<Py<PyAny>> {
            Ok(call_with(
                &dispatcher.getattr("subscribe_lifecycle")?,
                &[
                    ("subscriber", subscriber),
                    (
                        "accepts_opaque",
                        PyBool::new(py, false).to_owned().into_any(),
                    ),
                ],
            )?
            .unbind())
        };
        let unsubscribe_terminal_index: Py<PyAny> = subscribe(terminal_index.getattr("consume")?)?;
        let machine_output: bool = imported(py, NATIVE_MODULE, "machine_output_mode")?
            .call1((args,))?
            .is_truthy()?;
        let debug: Bound<'_, PyAny> = args.getattr("debug")?;
        let progress_on_stderr: bool =
            machine_output || debug.is_truthy()? || args.getattr("command")?.eq(DEBUG_COMMAND)?;
        let use_color: bool = !machine_output
            && !args.getattr("no_color")?.is_truthy()?
            && stdout_supports_color(py)?;
        let projector: Bound<'_, PyAny> = call_with(
            &imported(py, NATIVE_MODULE, "NativeProgressProjector")?,
            &[
                (
                    "stream",
                    py.import("sys")?.getattr(if progress_on_stderr {
                        "stderr"
                    } else {
                        "stdout"
                    })?,
                ),
                (
                    "use_color",
                    PyBool::new(py, use_color).to_owned().into_any(),
                ),
                ("debug", debug),
            ],
        )?;
        let unsubscribe_progress: Py<PyAny> = subscribe(projector.getattr("consume")?)?;
        let projector_token: Bound<'_, PyAny> = projector.call_method0("install")?;
        let mut observed: Observed = Observed {
            dispatcher: dispatcher.clone().unbind(),
            projector: projector.unbind(),
            projector_token: projector_token.unbind(),
            unsubscribe_terminal_index,
            unsubscribe_progress,
            outcome: Py::new(
                py,
                InvocationOutcome {
                    succeeded: AtomicBool::new(false),
                },
            )?,
            exporter_scope: None,
            unsubscribe_exporters: None,
            unsubscribe_outcome: None,
            entered: Vec::new(),
        };
        if let Err(error) = observed.install(py, (args, self.project_dir.bind(py)), &terminal_index)
        {
            let (raised, _) = observed.exit_contexts(py, Some(error));
            observed.release(py);
            return Err(raised
                .unwrap_or_else(|| PyRuntimeError::new_err("observability scope setup failed")));
        }
        *self.locked()? = Some(observed);
        Ok(dispatcher.unbind())
    }

    #[pyo3(signature = (*exc_info))]
    fn __exit__(&self, py: Python<'_>, exc_info: &Bound<'_, PyTuple>) -> PyResult<bool> {
        let Some(mut observed) = self.locked()?.take() else {
            return Ok(false);
        };
        let value: Bound<'_, PyAny> = exc_info.get_item(1)?;
        let pending: Option<PyErr> = if value.is_none() {
            None
        } else {
            Some(PyErr::from_value(value))
        };
        let had_error: bool = pending.is_some();
        let (raised, suppressed) = observed.exit_contexts(py, pending);
        observed.release(py);
        match raised {
            Some(error) if had_error => {
                let original: Bound<'_, PyAny> = exc_info.get_item(1)?;
                if error.value(py).is(&original) {
                    Ok(false)
                } else {
                    Err(error)
                }
            }
            Some(error) => Err(error),
            None => Ok(suppressed),
        }
    }
}

/// Install native progress, terminal indexing and configured event exporters for one command.
#[pyfunction]
#[pyo3(signature = (*, args, project_dir))]
pub(crate) fn cli_observability_scope(
    args: Py<PyAny>,
    project_dir: Py<PyAny>,
) -> CliObservabilityScope {
    CliObservabilityScope {
        args,
        project_dir,
        observed: Mutex::new(None),
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<CliObservabilityScope>()?;
    module.add_function(wrap_pyfunction!(cli_observability_scope, module)?)
}
