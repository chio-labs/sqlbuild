//! The macro call memo class: one compile's recorded calls and its optional native store.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::Python;
use pyo3::{PyResult, pyclass, pymethods};
use sqlbuild_cache::store::models::NativeStore;
use sqlbuild_render::macro_calls::models::MacroCallEntry;
use std::path::PathBuf;
use std::sync::Mutex;

use crate::bindings::_helpers::cache::native_store::{open_store, save_store};

use crate::bindings::_helpers::render::macro_call_rows::{EntryRow, event_from_row, event_row};

/// The native store kind holding recorded macro calls.
const MACRO_CALL_STORE_KIND: &str = "macro-calls";

/// The macro call results one compile records and replays, keyed by call class and call text.
#[pyclass(module = "sqlbuild._native", frozen)]
#[derive(Debug, Default)]
pub(crate) struct MacroCallMemo {
    pub(crate) inner: Mutex<sqlbuild_render::macro_calls::models::MacroCallMemo>,
}

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

    /// Open the store at `path` for `environment`; returns its saved metadata and entry count.
    fn attach_store(
        &self,
        py: Python<'_>,
        path: PathBuf,
        environment: &str,
    ) -> PyResult<(Vec<u8>, usize)> {
        let store: NativeStore = open_store(py, &path, MACRO_CALL_STORE_KIND, environment)?;
        let opened = (store.metadata().to_vec(), store.loaded_entries());
        self.inner.lock().map_err(poisoned)?.attach_store(store);
        Ok(opened)
    }

    /// Drop the attached store's loaded entries after its metadata failed validation.
    fn discard_store(&self) -> PyResult<()> {
        if let Some(store) = self.inner.lock().map_err(poisoned)?.store_mut() {
            store.discard();
        }
        Ok(())
    }

    /// Store results of `class_id` under `class_text` and everything the store key covers.
    fn set_persistent_class(&self, class_id: u64, class_text: &str) -> PyResult<()> {
        self.inner
            .lock()
            .map_err(poisoned)?
            .set_persistent_class(class_id, class_text);
        Ok(())
    }

    /// Calls found in the store and calls recorded into it.
    fn store_stats(&self) -> PyResult<(usize, usize)> {
        Ok(self.inner.lock().map_err(poisoned)?.store_stats())
    }

    /// Atomically save the store when this compile recorded into it; returns entries written.
    fn save_store(
        &self,
        py: Python<'_>,
        path: PathBuf,
        metadata: &[u8],
    ) -> PyResult<Option<usize>> {
        let mut memo = self.inner.lock().map_err(poisoned)?;
        let Some(store) = memo.store_mut() else {
            return Ok(None);
        };
        save_store(py, store, &path, metadata)
    }
}
