//! Whole per-file SQL-test scan results kept as one kind of the shared native store.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyclass, pymethods};
use sqlbuild_cache::digest::main::content_digest::content_digest;
use sqlbuild_cache::digest::types::ContentDigest;
use sqlbuild_cache::store::models::NativeStore;
use std::path::PathBuf;
use std::sync::Mutex;

use crate::bindings::_helpers::cache::native_store::{open_store, save_store};

/// The native store kind holding SQL-test scan results.
const SQL_TEST_SCAN_STORE_KIND: &str = "sql-test-scans";

/// One compile's view of the stored scan results, keyed by the digest of the caller's key parts.
#[pyclass(module = "sqlbuild._native", frozen)]
#[derive(Debug)]
pub(crate) struct SqlTestScanStore {
    store: Mutex<NativeStore>,
}

fn poisoned<T>(_: T) -> pyo3::PyErr {
    PyValueError::new_err("SQL test scan store is poisoned")
}

#[pymethods]
impl SqlTestScanStore {
    /// Open the store at `path` for `environment`; missing, damaged or foreign files open empty.
    #[new]
    fn new(py: Python<'_>, path: PathBuf, environment: &str) -> PyResult<Self> {
        let store: NativeStore = open_store(py, &path, SQL_TEST_SCAN_STORE_KIND, environment)?;
        Ok(Self {
            store: Mutex::new(store),
        })
    }

    /// The value stored under the digest of `key_parts`, or `None`.
    fn get(&self, key_parts: Vec<String>) -> PyResult<Option<Vec<u8>>> {
        let key: ContentDigest = content_digest(&key_parts);
        Ok(self
            .store
            .lock()
            .map_err(poisoned)?
            .get(&key)
            .map(<[u8]>::to_vec))
    }

    /// Store `value` under the digest of `key_parts`.
    fn put(&self, key_parts: Vec<String>, value: Vec<u8>) -> PyResult<()> {
        let key: ContentDigest = content_digest(&key_parts);
        self.store.lock().map_err(poisoned)?.put(key, value);
        Ok(())
    }

    /// Atomically save the store when this compile stored a value; returns entries written.
    fn save(&self, py: Python<'_>, path: PathBuf) -> PyResult<Option<usize>> {
        let store = self.store.lock().map_err(poisoned)?;
        save_store(py, &store, &path, &[])
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<SqlTestScanStore>()?;
    Ok(())
}
