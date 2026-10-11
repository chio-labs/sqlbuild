//! Whole per-file SQL-test scan results kept as one kind of the shared native store.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyclass, pymethods};
use sqlbuild_cache::digest::main::content_digest::content_digest;
use sqlbuild_cache::digest::types::ContentDigest;
use sqlbuild_cache::store::models::NativeStore;
use std::path::PathBuf;
use std::sync::Mutex;
use std::sync::atomic::{AtomicUsize, Ordering};

use crate::bindings::_helpers::cache::native_store::{open_store, save_store};

/// The native store kind holding SQL-test scan results.
const SQL_TEST_SCAN_STORE_KIND: &str = "sql-test-scans";

/// One compile's view of the stored scan results, keyed by the digest of the caller's key parts.
#[pyclass(module = "sqlbuild._native", frozen)]
#[derive(Debug)]
pub(crate) struct SqlTestScanStore {
    store: Mutex<NativeStore>,
    hits: AtomicUsize,
    misses: AtomicUsize,
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
            hits: AtomicUsize::new(0),
            misses: AtomicUsize::new(0),
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

    /// Count one read as a hit, when it decoded to a usable result, or a miss.
    fn record(&self, hit: bool) {
        let counter: &AtomicUsize = if hit { &self.hits } else { &self.misses };
        counter.fetch_add(1, Ordering::Relaxed);
    }

    /// The hits and misses counted by this compile.
    fn counts(&self) -> (usize, usize) {
        (
            self.hits.load(Ordering::Relaxed),
            self.misses.load(Ordering::Relaxed),
        )
    }

    /// Atomically save the store when this compile stored a value; returns entries written.
    fn save(&self, py: Python<'_>, path: PathBuf) -> PyResult<Option<usize>> {
        let store = self.store.lock().map_err(poisoned)?;
        save_store(py, &store, &path, &[])
    }
}

impl SqlTestScanStore {
    /// The stored value under `key_parts`, counted as a hit when `decode` accepts it.
    pub(crate) fn decoded<T>(
        &self,
        key_parts: Vec<String>,
        decode: impl FnOnce(&[u8]) -> Option<T>,
    ) -> PyResult<Option<T>> {
        let found: Option<Vec<u8>> = self.get(key_parts)?;
        let decoded: Option<T> = found.as_deref().and_then(decode);
        self.record(decoded.is_some());
        Ok(decoded)
    }

    /// Store one complete result under `key_parts`.
    pub(crate) fn stored(&self, key_parts: Vec<String>, value: Vec<u8>) -> PyResult<()> {
        self.put(key_parts, value)
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<SqlTestScanStore>()?;
    Ok(())
}
