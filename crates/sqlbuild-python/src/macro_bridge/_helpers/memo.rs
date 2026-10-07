//! Python methods of the in-compile macro call memo.

use pyo3::exceptions::PyValueError;
use pyo3::{PyResult, pymethods};
use sqlbuild_render::macro_calls::models::MacroCallEntry;

use crate::macro_bridge::_helpers::rows::{event_from_row, event_row};
use crate::macro_bridge::models::MacroCallMemo;
use crate::macro_bridge::types::EntryRow;

fn poisoned<T>(_: T) -> pyo3::PyErr {
    PyValueError::new_err("macro call memo is poisoned")
}

#[pymethods]
impl MacroCallMemo {
    #[new]
    fn new() -> Self {
        Self::default()
    }

    /// The recorded result of a call in `class_id`, or `None` when it must execute.
    fn lookup(&self, class_id: u64, call_text: &str) -> PyResult<Option<EntryRow>> {
        let found = self
            .inner
            .lock()
            .map_err(poisoned)?
            .lookup(class_id, call_text);
        Ok(found.map(|entry| {
            (
                entry.sql.clone(),
                entry.relations.clone(),
                entry.events.iter().map(event_row).collect(),
            )
        }))
    }

    /// Record the `(sql, relations, events)` result of one executed call.
    fn record(&self, class_id: u64, call_text: String, entry: EntryRow) -> PyResult<()> {
        let (sql, relations, events) = entry;
        let entry = MacroCallEntry {
            sql,
            relations,
            events: events
                .into_iter()
                .map(event_from_row)
                .collect::<PyResult<_>>()?,
        };
        self.inner
            .lock()
            .map_err(poisoned)?
            .record(class_id, call_text, entry);
        Ok(())
    }

    /// Hits, misses and recorded results so far.
    fn stats(&self) -> PyResult<(usize, usize, usize)> {
        Ok(self.inner.lock().map_err(poisoned)?.stats())
    }
}
