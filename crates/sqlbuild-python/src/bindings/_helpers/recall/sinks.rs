//! The native subscriber that publishes every lifecycle fact and artifact into Recall.

use std::sync::Arc;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python, pyclass, pymethods};
use pyo3::types::{PyString, PyStringMethods};
use sqlbuild_recall::writer::models::RecallSession;

use crate::bindings::_helpers::native_host::executor::ExecutorHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::recall::events::event_object;

/// Publishes lifecycle events and SQL artifacts of the active session; delivery is best effort.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct RecallLifecycleSink {
    pub(crate) session: Arc<RecallSession>,
}

#[pymethods]
impl RecallLifecycleSink {
    fn __call__(&self, py: Python<'_>, event: &Bound<'_, PyAny>) -> PyResult<()> {
        if let Some(object) = event_object(event)? {
            drop(self.session.publish_event_object(&object));
            return Ok(());
        }
        let encoded = host::entry(py, ExecutorHost::LifecycleEventToJson)?.call1((event,))?;
        let text = encoded
            .downcast::<PyString>()?
            .to_string_lossy()
            .into_owned();
        drop(self.session.publish_event(&text));
        Ok(())
    }

    #[pyo3(signature = (*, sql, statement_id=None, resource_id=None))]
    fn record_sql(&self, sql: &str, statement_id: Option<&str>, resource_id: Option<&str>) {
        self.session.publish_sql(sql, statement_id, resource_id);
    }
}
