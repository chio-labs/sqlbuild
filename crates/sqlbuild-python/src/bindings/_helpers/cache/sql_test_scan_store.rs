//! Whole per-file SQL-test scan results kept as one kind of the shared native store.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyclass, pymethods};
use sqlbuild_cache::digest::main::content_digest::content_digest;
use sqlbuild_cache::digest::main::hex_digest::hex_digest;
use sqlbuild_cache::digest::types::ContentDigest;
use sqlbuild_cache::store::models::NativeStore;
use std::path::PathBuf;
use std::sync::Mutex;
use std::sync::atomic::{AtomicUsize, Ordering};

use crate::bindings::_helpers::cache::native_store::{open_store, save_store};

/// The native store kind holding SQL-test scan results.
const SQL_TEST_SCAN_STORE_KIND: &str = "sql-test-scans";
/// The store file below the compile cache folder.
const SQL_TEST_SCAN_STORE_FILE_NAME: &str = "sql-test-scans.bin";
/// Bumped whenever stored scan values change shape; older stores open empty.
const SQL_TEST_SCAN_STORE_VERSION: &str = "sql-test-scan-store-v1";

/// One compile's view of the stored scan results, keyed by the digest of the caller's key parts.
#[pyclass(module = "sqlbuild._native", frozen)]
#[derive(Debug)]
pub(crate) struct SqlTestScanStore {
    store: Mutex<NativeStore>,
    path: PathBuf,
    hits: AtomicUsize,
    misses: AtomicUsize,
}

fn poisoned<T>(_: T) -> pyo3::PyErr {
    PyValueError::new_err("SQL test scan store is poisoned")
}

#[pymethods]
impl SqlTestScanStore {
    /// Open the compile cache folder's store for `code_identity`; the error when it cannot open.
    #[staticmethod]
    fn open_in(
        py: Python<'_>,
        cache_dir: PathBuf,
        code_identity: &str,
    ) -> (Option<Self>, Option<String>) {
        let path: PathBuf = cache_dir.join(SQL_TEST_SCAN_STORE_FILE_NAME);
        let environment: String = hex_digest(&content_digest(&[
            SQL_TEST_SCAN_STORE_VERSION,
            code_identity,
        ]));
        match open_store(py, &path, SQL_TEST_SCAN_STORE_KIND, &environment) {
            Ok(store) => (
                Some(Self {
                    store: Mutex::new(store),
                    path,
                    hits: AtomicUsize::new(0),
                    misses: AtomicUsize::new(0),
                }),
                None,
            ),
            Err(error) => (None, Some(error.to_string())),
        }
    }

    /// The hits and misses counted by this compile.
    fn counts(&self) -> (usize, usize) {
        (
            self.hits.load(Ordering::Relaxed),
            self.misses.load(Ordering::Relaxed),
        )
    }

    /// Atomically save values this compile stored; entries written, or the error that stopped it.
    fn save(&self, py: Python<'_>) -> PyResult<(Option<usize>, Option<String>)> {
        let store = self.store.lock().map_err(poisoned)?;
        Ok(match save_store(py, &store, &self.path, &[]) {
            Ok(written) => (written, None),
            Err(error) => (None, Some(error.to_string())),
        })
    }
}

impl SqlTestScanStore {
    /// The stored value under `key_parts`, counted as a hit when `decode` accepts it.
    pub(crate) fn decoded<T>(
        &self,
        key_parts: Vec<String>,
        decode: impl FnOnce(&[u8]) -> Option<T>,
    ) -> PyResult<Option<T>> {
        let key: ContentDigest = content_digest(&key_parts);
        let decoded: Option<T> = self
            .store
            .lock()
            .map_err(poisoned)?
            .get(&key)
            .and_then(decode);
        let counter: &AtomicUsize = if decoded.is_some() {
            &self.hits
        } else {
            &self.misses
        };
        counter.fetch_add(1, Ordering::Relaxed);
        Ok(decoded)
    }

    /// Store one complete result under `key_parts`.
    pub(crate) fn stored(&self, key_parts: Vec<String>, value: Vec<u8>) -> PyResult<()> {
        let key: ContentDigest = content_digest(&key_parts);
        self.store.lock().map_err(poisoned)?.put(key, value);
        Ok(())
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<SqlTestScanStore>()?;
    module.add(
        "SQL_TEST_SCAN_STORE_FILE_NAME",
        SQL_TEST_SCAN_STORE_FILE_NAME,
    )?;
    Ok(())
}
