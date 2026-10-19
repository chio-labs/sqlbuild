//! The native subscriber that publishes every lifecycle fact and artifact into Recall.

use std::sync::Arc;

use pyo3::exceptions::PyException;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python, pyclass, pymethods};
use pyo3::types::PyString;
use serde_json::{Map, Value};
use sqlbuild_recall::records::main::parse_event::parse_event;
use sqlbuild_recall::writer::models::RecallSession;

use crate::bindings::_helpers::native_host::executor::ExecutorHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::recall::events::{escaped_text, event_object};
use crate::bindings::_helpers::recall::replacements::RecallReplacements;

/// `event` as the JSON object `lifecycle_event_to_json` encodes; `None` when it cannot be encoded.
pub(crate) fn lifecycle_event_object(
    py: Python<'_>,
    event: &Bound<'_, PyAny>,
) -> PyResult<Option<Map<String, Value>>> {
    if let Some(object) = event_object(event)? {
        return Ok(Some(object));
    }
    let encoded = host::entry(py, ExecutorHost::LifecycleEventToJson)?.call1((event,))?;
    let text = escaped_text(encoded.downcast::<PyString>()?)?;
    match parse_event(&text) {
        Ok(object) => Ok(Some(object)),
        Err(_unencodable) => Ok(None),
    }
}

/// Queue `event` in `session`; an event that cannot be encoded is skipped.
pub(crate) fn publish_lifecycle_event(
    py: Python<'_>,
    session: &RecallSession,
    event: &Bound<'_, PyAny>,
) -> PyResult<()> {
    if let Some(object) = lifecycle_event_object(py, event)? {
        session.publish_event_object(object);
    }
    Ok(())
}

/// Publishes lifecycle events, through the Recall replacement sink on the delivery thread when one is configured, and SQL artifacts of the active session; delivery is best effort.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct RecallLifecycleSink {
    pub(crate) session: Arc<RecallSession>,
    pub(crate) replacements: Arc<RecallReplacements>,
}

#[pymethods]
impl RecallLifecycleSink {
    /// Record `event`; an event Recall cannot encode is skipped, never raised into the command.
    fn __call__(&self, py: Python<'_>, event: &Bound<'_, PyAny>) -> PyResult<()> {
        recording(py, self.publish(py, event))
    }

    /// Record one SQL artifact; text Recall cannot encode is skipped, never raised into the command.
    #[pyo3(signature = (*, sql, statement_id=None, resource_id=None))]
    fn record_sql(
        &self,
        py: Python<'_>,
        sql: &Bound<'_, PyString>,
        statement_id: Option<&Bound<'_, PyString>>,
        resource_id: Option<&Bound<'_, PyString>>,
    ) -> PyResult<()> {
        let texts = (|| -> PyResult<(String, Option<String>, Option<String>)> {
            Ok((
                escaped_text(sql)?,
                statement_id.map(escaped_text).transpose()?,
                resource_id.map(escaped_text).transpose()?,
            ))
        })();
        recording(
            py,
            texts.map(|(sql, statement_id, resource_id)| {
                self.session
                    .publish_sql(&sql, statement_id.as_deref(), resource_id.as_deref());
            }),
        )
    }
}

impl RecallLifecycleSink {
    fn publish(&self, py: Python<'_>, event: &Bound<'_, PyAny>) -> PyResult<()> {
        if self
            .replacements
            .deliver_lifecycle(py, &self.session, event)?
        {
            return Ok(());
        }
        publish_lifecycle_event(py, &self.session, event)
    }
}

/// `outcome` with ordinary exceptions dropped, so recording never changes what the command raises; interrupts still propagate.
fn recording(py: Python<'_>, outcome: PyResult<()>) -> PyResult<()> {
    match outcome {
        Err(error) if error.is_instance_of::<PyException>(py) => Ok(()),
        other => other,
    }
}
