//! Register `_native.HOST_ENTRIES`, the host table the Python import test checks against.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::types::PyTuple;

use crate::bindings::_helpers::native_host::constants::HOST_ENTRIES;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let entries: Vec<(&str, &str, &str)> = HOST_ENTRIES
        .iter()
        .flat_map(|group| group.iter())
        .map(|entry| (entry.name, entry.kind.label(), entry.edge.label()))
        .collect();
    module.add("HOST_ENTRIES", PyTuple::new(module.py(), entries)?)
}
