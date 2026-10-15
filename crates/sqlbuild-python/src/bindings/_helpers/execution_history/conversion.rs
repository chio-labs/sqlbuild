//! Execution history models, timestamps, SQL parameters and errors across the Python boundary.

use pyo3::IntoPyObjectExt;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyBool, PyInt, PyList, PyString, PyStringMethods, PyTuple};
use sqlbuild_state::execution_history::constants::ENVELOPE_TEXT_FIELDS;
use sqlbuild_state::execution_history::errors::{HistoryError, HistoryErrorKind};
use sqlbuild_state::execution_history::models::{
    EventEnvelope, EventFilterSpec, FilterTime, ProjectionFact, RunFact, RunFilterSpec, RunRow,
    RunStatus, SqlParam,
};
use sqlbuild_state::execution_history::types::UtcTime;

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::cursor::values::{DATETIME_MODULE, local_date_time};

pub(crate) const EXCEPTIONS_MODULE: &str = "sqlbuild.runtime.execution_history.exceptions";
pub(crate) const MODELS_MODULE: &str = "sqlbuild.runtime.execution_history.models";
const TYPES_MODULE: &str = "sqlbuild.runtime.execution_history.types";
const EVENT_MODELS_MODULE: &str = "sqlbuild.runtime.observability.models";
const EVENT_TO_JSON_MODULE: &str = "sqlbuild.runtime.observability.main.lifecycle_event_to_json";
const EVENT_FROM_JSON_MODULE: &str =
    "sqlbuild.runtime.observability.main.lifecycle_event_from_json";
const UTC_SUFFIX: &str = "Z";
const UTC_OFFSET: &str = "+00:00";
const DEFAULT_SCHEMA_VERSION: i64 = 1;
const UTC_OFFSET_SECONDS: f64 = 0.0;

fn exception_name(kind: HistoryErrorKind) -> &'static str {
    match kind {
        HistoryErrorKind::Storage => "ExecutionHistoryStorageError",
        HistoryErrorKind::IntegrityConflict => "IntegrityConflictError",
        HistoryErrorKind::InvalidEvent => "InvalidEventError",
        HistoryErrorKind::InvalidCursor => "InvalidCursorError",
        HistoryErrorKind::InvalidFilter => "InvalidFilterError",
        HistoryErrorKind::InvalidLimit => "InvalidLimitError",
        HistoryErrorKind::UnsupportedSchemaVersion => "UnsupportedSchemaVersionError",
        HistoryErrorKind::ProjectionConsistency => "ProjectionConsistencyError",
    }
}

/// The execution history exception for a rejection of `kind`.
pub(crate) fn rejection(py: Python<'_>, kind: HistoryErrorKind, message: &str) -> PyErr {
    match imported(py, EXCEPTIONS_MODULE, exception_name(kind))
        .and_then(|class| class.call1((message,)))
    {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}

/// An `ExecutionHistoryStorageError`.
pub(crate) fn storage_error(py: Python<'_>, message: &str) -> PyErr {
    rejection(py, HistoryErrorKind::Storage, message)
}

/// An `ExecutionHistoryStorageError` raised `from cause`.
pub(crate) fn storage_error_from(py: Python<'_>, message: &str, cause: PyErr) -> PyErr {
    let error: PyErr = storage_error(py, message);
    error.set_cause(py, Some(cause));
    error
}

/// `result`, with a history rejection raised as its Python exception.
pub(crate) fn checked<T>(py: Python<'_>, result: Result<T, HistoryError>) -> PyResult<T> {
    result.map_err(|error| rejection(py, error.kind, &error.message))
}

/// Whether `error` is an instance of the execution history exception named `name`.
pub(crate) fn history_error_of_kind(py: Python<'_>, error: &PyErr, name: &str) -> PyResult<bool> {
    Ok(error.is_instance(py, &imported(py, EXCEPTIONS_MODULE, name)?))
}

/// `value` when it is an `int` other than `bool` that fits, as `isinstance(value, int)` checks.
pub(crate) fn exact_int(value: &Bound<'_, PyAny>) -> Option<i64> {
    if !value.is_instance_of::<PyInt>() || value.is_instance_of::<PyBool>() {
        return None;
    }
    value.extract().unwrap_or(None)
}

/// `value` as text when it is a `str`.
pub(crate) fn text_of(value: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    match value.downcast::<PyString>() {
        Ok(text) => Ok(Some(text.to_str()?.to_owned())),
        Err(_) => Ok(None),
    }
}

/// `value` as text, or `None` when it is `None`.
pub(crate) fn optional_text(value: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if value.is_none() {
        return Ok(None);
    }
    Ok(Some(value.extract()?))
}

/// `datetime.UTC`.
pub(crate) fn utc(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    imported(py, DATETIME_MODULE, "UTC")
}

/// An aware `datetime` as its UTC wall time.
pub(crate) fn utc_time(value: &Bound<'_, PyAny>) -> PyResult<UtcTime> {
    local_date_time(&value.call_method1("astimezone", (utc(value.py())?,))?)
}

/// A UTC `datetime` at `value`.
pub(crate) fn python_time<'py>(py: Python<'py>, value: &UtcTime) -> PyResult<Bound<'py, PyAny>> {
    imported(py, DATETIME_MODULE, "datetime")?.call1((
        value.date.year,
        value.date.month,
        value.date.day,
        value.hour,
        value.minute,
        value.second,
        value.microsecond,
        utc(py)?,
    ))
}

/// `datetime.now(UTC)`.
pub(crate) fn now(py: Python<'_>) -> PyResult<UtcTime> {
    let current = imported(py, DATETIME_MODULE, "datetime")?.call_method1("now", (utc(py)?,))?;
    local_date_time(&current)
}

/// Whether a `datetime`'s `tzinfo` is exactly `UTC`.
pub(crate) fn utc_zone(value: &Bound<'_, PyAny>) -> PyResult<bool> {
    Ok(value.getattr("tzinfo")?.is(&utc(value.py())?))
}

/// `datetime.fromisoformat(text.replace("Z", "+00:00"))`, or `None` on `ValueError`.
pub(crate) fn parsed_iso<'py>(py: Python<'py>, text: &str) -> PyResult<Option<Bound<'py, PyAny>>> {
    let normalized: String = text.replace(UTC_SUFFIX, UTC_OFFSET);
    match imported(py, DATETIME_MODULE, "datetime")?.call_method1("fromisoformat", (normalized,)) {
        Ok(value) => Ok(Some(value)),
        Err(error) if error.is_instance_of::<PyValueError>(py) => Ok(None),
        Err(error) => Err(error),
    }
}

fn filter_time(value: &Bound<'_, PyAny>) -> PyResult<Option<FilterTime>> {
    if value.is_none() {
        return Ok(None);
    }
    Ok(Some(FilterTime {
        instant: utc_time(value)?,
        is_utc: utc_zone(value)?,
    }))
}

fn texts(value: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    value
        .try_iter()?
        .map(|item| item.and_then(|item| item.extract()))
        .collect()
}

/// An `EventFilter`'s fields.
pub(crate) fn event_filter_spec(value: &Bound<'_, PyAny>) -> PyResult<EventFilterSpec> {
    let family: Bound<'_, PyAny> = value.getattr("family")?;
    Ok(EventFilterSpec {
        invocation_id: optional_text(&value.getattr("invocation_id")?)?,
        run_id: optional_text(&value.getattr("run_id")?)?,
        producer: optional_text(&value.getattr("producer")?)?,
        event_types: texts(&value.getattr("event_types")?)?,
        family: if family.is_none() {
            None
        } else {
            Some(family.getattr("value")?.extract()?)
        },
        occurred_at_start: filter_time(&value.getattr("occurred_at_start")?)?,
        occurred_at_end: filter_time(&value.getattr("occurred_at_end")?)?,
    })
}

/// A `RunStatus` member's status.
fn run_status(value: &Bound<'_, PyAny>) -> PyResult<RunStatus> {
    let text: String = value.getattr("value")?.extract()?;
    parsed_status(value.py(), &text)
}

/// The status named by stored `text`, as `RunStatus(text)` accepts it.
pub(crate) fn parsed_status(py: Python<'_>, text: &str) -> PyResult<RunStatus> {
    let known: Option<RunStatus> = [RunStatus::Unknown, RunStatus::Completed, RunStatus::Failed]
        .into_iter()
        .find(|status| status.value() == text);
    if let Some(status) = known {
        return Ok(status);
    }
    imported(py, TYPES_MODULE, "RunStatus")?.call1((text,))?;
    Ok(RunStatus::Unknown)
}

/// A `RunFilter`'s fields.
pub(crate) fn run_filter_spec(value: &Bound<'_, PyAny>) -> PyResult<RunFilterSpec> {
    let statuses: Vec<RunStatus> = value
        .getattr("statuses")?
        .try_iter()?
        .map(|item| item.and_then(|item| run_status(&item)))
        .collect::<PyResult<_>>()?;
    Ok(RunFilterSpec {
        invocation_id: optional_text(&value.getattr("invocation_id")?)?,
        statuses,
        created_at_start: filter_time(&value.getattr("created_at_start")?)?,
        created_at_end: filter_time(&value.getattr("created_at_end")?)?,
    })
}

/// Whether `event` is a known-schema `LifecycleEvent`.
pub(crate) fn known_event(event: &Bound<'_, PyAny>) -> PyResult<bool> {
    event.is_instance(&imported(
        event.py(),
        EVENT_MODELS_MODULE,
        "LifecycleEvent",
    )?)
}

/// The `event_id` a known event carries or an opaque envelope holds as a string.
pub(crate) fn event_id_of(event: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if known_event(event)? {
        return text_of(&event.getattr("event_id")?);
    }
    text_of(&raw_field(event, "event_id")?)
}

fn raw_field<'py>(event: &Bound<'py, PyAny>, name: &str) -> PyResult<Bound<'py, PyAny>> {
    event.getattr("raw")?.call_method1("get", (name,))
}

/// `lifecycle_event_to_json(event)`.
pub(crate) fn event_json(event: &Bound<'_, PyAny>) -> PyResult<String> {
    imported(event.py(), EVENT_TO_JSON_MODULE, "lifecycle_event_to_json")?
        .call1((event,))?
        .extract()
}

/// `lifecycle_event_from_json(payload)`.
pub(crate) fn event_from_json<'py>(payload: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    imported(
        payload.py(),
        EVENT_FROM_JSON_MODULE,
        "lifecycle_event_from_json",
    )?
    .call1((payload,))
}

/// An opaque envelope's `occurred_at` when it is ISO text with a zero UTC offset.
fn opaque_occurred_at(event: &Bound<'_, PyAny>) -> PyResult<Option<UtcTime>> {
    let py: Python<'_> = event.py();
    let Some(text) = text_of(&raw_field(event, "occurred_at")?)? else {
        return Ok(None);
    };
    let Some(parsed) = parsed_iso(py, &text)? else {
        return Ok(None);
    };
    let offset: Bound<'_, PyAny> = parsed.call_method0("utcoffset")?;
    if offset.is_none()
        || offset.call_method0("total_seconds")?.extract::<f64>()? != UTC_OFFSET_SECONDS
    {
        return Ok(None);
    }
    Ok(Some(utc_time(&parsed)?))
}

/// The stable envelope fields stored next to an event.
pub(crate) fn envelope_of(event: &Bound<'_, PyAny>) -> PyResult<EventEnvelope> {
    let mut envelope = EventEnvelope::default();
    if known_event(event)? {
        envelope.schema_version = event.getattr("schema_version")?.extract()?;
        for (slot, name) in envelope.text_fields.iter_mut().zip(ENVELOPE_TEXT_FIELDS) {
            *slot = optional_text(&event.getattr(name)?)?;
        }
        envelope.occurred_at = Some(utc_time(&event.getattr("occurred_at")?)?);
        return Ok(envelope);
    }
    envelope.schema_version =
        exact_int(&raw_field(event, "schema_version")?).unwrap_or(DEFAULT_SCHEMA_VERSION);
    for (slot, name) in envelope.text_fields.iter_mut().zip(ENVELOPE_TEXT_FIELDS) {
        *slot = text_of(&raw_field(event, name)?)?.filter(|text| !text.is_empty());
    }
    envelope.occurred_at = opaque_occurred_at(event)?;
    Ok(envelope)
}

/// A `StoredEvent` as projection reads it.
pub(crate) fn projection_fact(stored: &Bound<'_, PyAny>) -> PyResult<ProjectionFact> {
    let event: Bound<'_, PyAny> = stored.getattr("event")?;
    let mut run: Option<RunFact> = None;
    if known_event(&event)? {
        let run_id: Bound<'_, PyAny> = event.getattr("run_id")?;
        if !run_id.is_none() {
            run = Some(RunFact {
                run_id: run_id.extract()?,
                invocation_id: event.getattr("invocation_id")?.extract()?,
                event_type: event.getattr("event_type")?.extract()?,
                occurred_at: utc_time(&event.getattr("occurred_at")?)?,
            });
        }
    }
    Ok(ProjectionFact {
        storage_order: stored.getattr("storage_order")?.extract()?,
        cursor: stored.getattr("cursor")?.extract()?,
        received_at: utc_time(&stored.getattr("received_at")?)?,
        run,
    })
}

/// A `RunRecord` as a projected run.
pub(crate) fn run_row(record: &Bound<'_, PyAny>) -> PyResult<RunRow> {
    let optional_time = |name: &str| -> PyResult<Option<UtcTime>> {
        let value: Bound<'_, PyAny> = record.getattr(name)?;
        if value.is_none() {
            return Ok(None);
        }
        utc_time(&value).map(Some)
    };
    Ok(RunRow {
        run_id: record.getattr("run_id")?.extract()?,
        invocation_id: record.getattr("invocation_id")?.extract()?,
        created_at: utc_time(&record.getattr("created_at")?)?,
        status: run_status(&record.getattr("status")?)?,
        is_complete: record.getattr("is_complete")?.is_truthy()?,
        last_event_cursor: record.getattr("last_event_cursor")?.extract()?,
        last_storage_order: record.getattr("last_storage_order")?.extract()?,
        command: optional_text(&record.getattr("command")?)?,
        target: optional_text(&record.getattr("target")?)?,
        environment: optional_text(&record.getattr("environment")?)?,
        started_at: optional_time("started_at")?,
        ended_at: optional_time("ended_at")?,
    })
}

fn optional_python_time<'py>(
    py: Python<'py>,
    value: Option<&UtcTime>,
) -> PyResult<Bound<'py, PyAny>> {
    match value {
        Some(value) => python_time(py, value),
        None => Ok(py.None().into_bound(py)),
    }
}

/// The `RunRecord` of a projected run.
pub(crate) fn run_record<'py>(py: Python<'py>, run: &RunRow) -> PyResult<Bound<'py, PyAny>> {
    let status = imported(py, TYPES_MODULE, "RunStatus")?.call1((run.status.value(),))?;
    call_with(
        &imported(py, MODELS_MODULE, "RunRecord")?,
        &[
            ("run_id", run.run_id.clone().into_bound_py_any(py)?),
            (
                "invocation_id",
                run.invocation_id.clone().into_bound_py_any(py)?,
            ),
            ("created_at", python_time(py, &run.created_at)?),
            ("status", status),
            ("is_complete", run.is_complete.into_bound_py_any(py)?),
            (
                "last_event_cursor",
                run.last_event_cursor.clone().into_bound_py_any(py)?,
            ),
            (
                "last_storage_order",
                run.last_storage_order.into_bound_py_any(py)?,
            ),
            ("command", run.command.clone().into_bound_py_any(py)?),
            ("target", run.target.clone().into_bound_py_any(py)?),
            (
                "environment",
                run.environment.clone().into_bound_py_any(py)?,
            ),
            (
                "started_at",
                optional_python_time(py, run.started_at.as_ref())?,
            ),
            ("ended_at", optional_python_time(py, run.ended_at.as_ref())?),
        ],
    )
}

/// A tuple of the `RunRecord`s of projected runs.
pub(crate) fn run_records<'py>(py: Python<'py>, runs: &[RunRow]) -> PyResult<Bound<'py, PyTuple>> {
    let records: Vec<Bound<'py, PyAny>> = runs
        .iter()
        .map(|run| run_record(py, run))
        .collect::<PyResult<_>>()?;
    PyTuple::new(py, records)
}

/// The projected runs of an iterable of `RunRecord`s.
pub(crate) fn run_rows(records: &Bound<'_, PyAny>) -> PyResult<Vec<RunRow>> {
    records
        .try_iter()?
        .map(|record| record.and_then(|record| run_row(&record)))
        .collect()
}

/// The projection facts of an iterable of `StoredEvent`s.
pub(crate) fn projection_facts(stored: &Bound<'_, PyAny>) -> PyResult<Vec<ProjectionFact>> {
    stored
        .try_iter()?
        .map(|item| item.and_then(|item| projection_fact(&item)))
        .collect()
}

/// A `StoredEvent` decoded from its durable columns.
pub(crate) fn stored_event<'py>(
    py: Python<'py>,
    (storage_order, cursor): (i64, String),
    received_at: Bound<'py, PyAny>,
    payload: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    call_with(
        &imported(py, MODELS_MODULE, "StoredEvent")?,
        &[
            ("storage_order", storage_order.into_bound_py_any(py)?),
            ("cursor", cursor.into_bound_py_any(py)?),
            ("received_at", received_at),
            ("event", event_from_json(payload)?),
        ],
    )
}

/// A SQL parameter as the driver binds it.
pub(crate) fn python_param<'py>(py: Python<'py>, param: &SqlParam) -> PyResult<Bound<'py, PyAny>> {
    match param {
        SqlParam::Null => Ok(py.None().into_bound(py)),
        SqlParam::Text(text) => text.clone().into_bound_py_any(py),
        SqlParam::Integer(value) => value.into_bound_py_any(py),
        SqlParam::Flag(value) => value.into_bound_py_any(py),
        SqlParam::Timestamp(value) => python_time(py, value),
        SqlParam::TextList(values) => Ok(PyList::new(py, values)?.into_any()),
    }
}

/// The parameters of a query as a tuple.
pub(crate) fn python_params<'py>(
    py: Python<'py>,
    params: &[SqlParam],
) -> PyResult<Bound<'py, PyTuple>> {
    let values: Vec<Bound<'py, PyAny>> = params
        .iter()
        .map(|param| python_param(py, param))
        .collect::<PyResult<_>>()?;
    PyTuple::new(py, values)
}

/// `uuid.uuid4().hex`.
pub(crate) fn new_namespace(py: Python<'_>) -> PyResult<String> {
    imported(py, "uuid", "uuid4")?
        .call0()?
        .getattr("hex")?
        .extract()
}
