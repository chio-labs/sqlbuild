//! Recall replacement sinks: the one lifecycle and one command-output sink that decide what Recall stores.

use std::cell::Cell;
use std::sync::{Arc, OnceLock};

use pyo3::IntoPyObjectExt;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyBytes, PyDict, PyDictMethods, PyString};
use sqlbuild_core::command_output::constants::RECALL_REPLACEMENT_SCHEMA_VERSION;
use sqlbuild_core::command_output::main::ansi_free_text::ansi_free_text;
use sqlbuild_core::event_export::main::route_lifecycle_event::route_lifecycle_event;
use sqlbuild_core::event_export::models::{ExporterCounts, ExporterFilter};
use sqlbuild_recall::records::models::{OutputChunk, OutputStream};
use sqlbuild_recall::writer::models::{DeliveryStream, RecallSession, ReplacedOutput};
use sqlbuild_recall::writer::types::OutputReplacement;

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::event_exporting::models::BoundEventExporter;
use crate::bindings::_helpers::event_exporting::values::export_policy;
use crate::bindings::_helpers::native_host::executor::ExecutorHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::native_host::user_code::UserCodeHost;
use crate::bindings::_helpers::native_threads::constants::OUTPUT_SUPPRESSED_ATTRIBUTE;
use crate::bindings::_helpers::output_capture::records::invocation_context;
use crate::bindings::_helpers::recall::constants::{
    EVENT_PARAMETER, RECORD_PARAMETER, UTC_OFFSET, UTC_SUFFIX,
};
use crate::bindings::_helpers::recall::writer::RecallWriter;
use crate::bindings::_helpers::records::fields::field as native_field;

thread_local! {
    /// Set while this thread runs the output replacement sink, whose own writes Recall never records.
    static IN_OUTPUT_REPLACEMENT: Cell<bool> = const { Cell::new(false) };
}

/// Whether the current thread is running the output replacement sink.
pub(crate) fn in_output_replacement() -> bool {
    IN_OUTPUT_REPLACEMENT.with(Cell::get)
}

/// The lifecycle replacement: the sink function, the parameter its writer goes in, and its event filter.
struct LifecycleReplacement {
    function: Py<PyAny>,
    writer_parameter: String,
    filter: ExporterFilter,
}

/// The replacement sinks of one invocation, configured once discovery has run.
#[derive(Default)]
pub(crate) struct RecallReplacements {
    lifecycle: OnceLock<LifecycleReplacement>,
}

impl std::fmt::Debug for RecallReplacements {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("RecallReplacements")
            .field("lifecycle", &self.lifecycle.get().is_some())
            .finish()
    }
}

/// `function(**{parameter: record, writer_parameter: writer})` through the user-code shim; whether it raised.
fn invoke(
    py: Python<'_>,
    function: &Py<PyAny>,
    (parameter, record): (&str, &Bound<'_, PyAny>),
    (writer_parameter, writer): (&str, Bound<'_, PyAny>),
) -> PyResult<bool> {
    let arguments = PyDict::new(py);
    arguments.set_item(parameter, record)?;
    arguments.set_item(writer_parameter, writer)?;
    call_with(
        &host::entry(py, UserCodeHost::InvokeRecallSink)?,
        &[
            ("function", function.bind(py).clone()),
            ("arguments", arguments.into_any()),
        ],
    )?
    .extract()
}

/// The `(sink, writer_parameter)` pair discovery found, or `None`.
fn discovered<'py>(pair: &Bound<'py, PyAny>) -> PyResult<Option<(Bound<'py, PyAny>, String)>> {
    if pair.is_none() {
        return Ok(None);
    }
    let (sink, writer_parameter): (Bound<'py, PyAny>, String) = pair.extract()?;
    Ok(Some((sink, writer_parameter)))
}

impl RecallReplacements {
    /// Install the discovered replacements, each `(sink, writer_parameter)` or `None`; whether any filters Recall history.
    pub(crate) fn configure(
        &self,
        session: &Arc<RecallSession>,
        (lifecycle, output): (&Bound<'_, PyAny>, &Bound<'_, PyAny>),
    ) -> PyResult<bool> {
        let mut active: bool = false;
        if let Some((sink, writer_parameter)) = discovered(lifecycle)? {
            let bound = BoundEventExporter::create(
                native_field(&sink, "name")?.extract()?,
                (
                    native_field(&sink, "function")?.unbind(),
                    PyDict::new(sink.py()).into_any().unbind(),
                ),
                (
                    Some(&native_field(&sink, "event_kinds")?),
                    Some(&native_field(&sink, "min_severity")?),
                ),
            )?;
            drop(self.lifecycle.set(LifecycleReplacement {
                function: bound.function,
                writer_parameter,
                filter: bound.filter,
            }));
            active = true;
        }
        if let Some((sink, writer_parameter)) = discovered(output)? {
            let mut streams: [bool; 2] = [false; 2];
            for stream in native_field(&sink, "streams")?.try_iter()? {
                let name: String = native_field(&stream?, "value")?.extract()?;
                if let Some(stream) = OutputStream::from_name(&name) {
                    streams[usize::from(stream == OutputStream::Stderr)] = true;
                }
            }
            session.set_output_replacement(Arc::new(OutputSink {
                function: native_field(&sink, "function")?.unbind(),
                writer_parameter,
                streams,
                invocation_id: session.invocation_id(),
            }));
            active = true;
        }
        Ok(active)
    }

    /// Hand `event` to the lifecycle replacement and account for what it kept; `false` when there is none.
    pub(crate) fn deliver_lifecycle(
        &self,
        py: Python<'_>,
        session: &Arc<RecallSession>,
        event: &Bound<'_, PyAny>,
    ) -> PyResult<bool> {
        let Some(replacement) = self.lifecycle.get() else {
            return Ok(false);
        };
        let event_type: String = native_field(event, "event_type")?.extract()?;
        let eligible: bool = export_policy(py, &event_type).is_ok_and(|policy| {
            let (_, eligible) = route_lifecycle_event(
                &policy,
                std::slice::from_ref(&replacement.filter),
                vec![ExporterCounts::default()],
            );
            !eligible.is_empty()
        });
        if !eligible {
            session.record_filtered(DeliveryStream::Events, 1);
            return Ok(true);
        }
        let writer = Bound::new(py, RecallWriter::lifecycle(Arc::clone(session)))?;
        let raised: PyResult<bool> = invoke(
            py,
            &replacement.function,
            (EVENT_PARAMETER, event),
            (&replacement.writer_parameter, writer.clone().into_any()),
        );
        let (published, _) = writer.get().finish();
        match raised {
            Ok(false) if published == 0 => session.record_filtered(DeliveryStream::Events, 1),
            Ok(false) => {}
            Ok(true) | Err(_) => session.record_failed(DeliveryStream::Events, 1),
        }
        Ok(true)
    }
}

/// The output replacement, called on the Recall delivery thread for each chunk.
struct OutputSink {
    function: Py<PyAny>,
    writer_parameter: String,
    /// Whether the sink takes stdout and stderr chunks; others are filtered.
    streams: [bool; 2],
    invocation_id: String,
}

impl std::fmt::Debug for OutputSink {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("OutputSink")
            .field("writer_parameter", &self.writer_parameter)
            .field("streams", &self.streams)
            .finish_non_exhaustive()
    }
}

impl OutputSink {
    /// The schema-2 `CommandOutputRecord` of `chunk`.
    fn record<'py>(&self, py: Python<'py>, chunk: &OutputChunk) -> PyResult<Bound<'py, PyAny>> {
        let occurred_at: Bound<'py, PyAny> = imported(py, "datetime", "datetime")?.call_method1(
            "fromisoformat",
            (chunk.occurred_at.replace(UTC_SUFFIX, UTC_OFFSET),),
        )?;
        let context: Bound<'py, PyAny> =
            invocation_context(py, None).unwrap_or_else(|_| PyDict::new(py).into_any());
        call_with(
            &host::entry(py, ExecutorHost::CommandOutputRecord)?,
            &[
                (
                    "invocation_id",
                    PyString::new(py, &self.invocation_id).into_any(),
                ),
                ("sequence", chunk.sequence.into_bound_py_any(py)?),
                ("occurred_at", occurred_at),
                (
                    "stream",
                    host::entry(py, ExecutorHost::CommandOutputStream)?
                        .call1((chunk.stream.as_str(),))?,
                ),
                (
                    "message",
                    PyString::new(py, &ansi_free_text(&chunk.data)).into_any(),
                ),
                ("external_context", context),
                ("data", PyBytes::new(py, &chunk.data).into_any()),
                (
                    "schema_version",
                    RECALL_REPLACEMENT_SCHEMA_VERSION.into_bound_py_any(py)?,
                ),
            ],
        )
    }

    fn call(&self, py: Python<'_>, chunk: &OutputChunk) -> PyResult<ReplacedOutput> {
        if let Ok(thread) =
            imported(py, "threading", "current_thread").and_then(|current| current.call0())
        {
            thread.setattr(OUTPUT_SUPPRESSED_ATTRIBUTE, true)?;
        }
        let record = self.record(py, chunk)?;
        let writer = Bound::new(py, RecallWriter::output(chunk.sequence))?;
        let raised: bool = invoke(
            py,
            &self.function,
            (RECORD_PARAMETER, &record),
            (&self.writer_parameter, writer.clone().into_any()),
        )?;
        let (_, published) = writer.get().finish();
        Ok(match (raised, published) {
            (true, _) => ReplacedOutput::Failed,
            (false, Some(data)) => ReplacedOutput::Published(data),
            (false, None) => ReplacedOutput::Filtered,
        })
    }
}

impl OutputReplacement for OutputSink {
    fn replace(&self, chunk: &OutputChunk) -> ReplacedOutput {
        if !self.streams[usize::from(chunk.stream == OutputStream::Stderr)] {
            return ReplacedOutput::Filtered;
        }
        IN_OUTPUT_REPLACEMENT.with(|flag| flag.set(true));
        let replaced = Python::attach(|py| self.call(py, chunk)).unwrap_or(ReplacedOutput::Failed);
        IN_OUTPUT_REPLACEMENT.with(|flag| flag.set(false));
        replaced
    }
}
