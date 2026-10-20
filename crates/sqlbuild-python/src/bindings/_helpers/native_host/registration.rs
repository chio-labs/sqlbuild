//! Register `_native.HOST_ENTRIES`, the host table the Python import test checks against.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::types::PyTuple;
use sqlbuild_host::entries::main::host_entry_labels::host_entry_labels;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add(
        "HOST_ENTRIES",
        PyTuple::new(module.py(), host_entry_labels())?,
    )
}
