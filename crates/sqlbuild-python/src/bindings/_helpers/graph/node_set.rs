//! A Python set as the visited nodes of a native graph walk over Python keys.

use pyo3::PyErr;
use pyo3::prelude::{Bound, PyAny};
use pyo3::types::{PySet, PySetMethods};
use sqlbuild_core::graph_walk::types::NodeSet;

/// Python keys a walk visited, compared with Python hashing and equality.
pub(crate) struct PyNodeSet<'py>(pub(crate) Bound<'py, PySet>);

impl<'py> NodeSet<Bound<'py, PyAny>> for PyNodeSet<'py> {
    type Error = PyErr;

    fn insert_new(&mut self, key: &Bound<'py, PyAny>) -> Result<bool, PyErr> {
        if self.0.contains(key)? {
            return Ok(false);
        }
        self.0.add(key)?;
        Ok(true)
    }

    fn holds(&self, key: &Bound<'py, PyAny>) -> Result<bool, PyErr> {
        self.0.contains(key)
    }
}
