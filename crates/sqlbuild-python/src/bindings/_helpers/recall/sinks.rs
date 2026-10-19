//! The native subscriber that publishes every lifecycle fact and artifact into Recall.

use std::sync::Arc;

use pyo3::exceptions::PyException;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python, pyclass, pymethods};
use pyo3::types::PyString;
use sqlbuild_recall::writer::models::RecallSession;

use crate::bindings::_helpers::native_host::executor::ExecutorHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::recall::events::{escaped_text, event_object};

/// Publishes lifecycle events and SQL artifacts of the active session; delivery is best effort.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct RecallLifecycleSink {
    pub(crate) session: Arc<RecallSession>,
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
        if let Some(object) = event_object(event)? {
            self.session.publish_event_object(object);
            return Ok(());
        }
        let encoded = host::entry(py, ExecutorHost::LifecycleEventToJson)?.call1((event,))?;
        let text = escaped_text(encoded.downcast::<PyString>()?)?;
        drop(self.session.publish_event(&text));
        Ok(())
    }
}

/// `outcome` with ordinary exceptions dropped, so recording never changes what the command raises; interrupts still propagate.
fn recording(py: Python<'_>, outcome: PyResult<()>) -> PyResult<()> {
    match outcome {
        Err(error) if error.is_instance_of::<PyException>(py) => Ok(()),
        other => other,
    }
}
