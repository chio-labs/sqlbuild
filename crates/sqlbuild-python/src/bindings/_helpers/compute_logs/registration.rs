//! Register the native compute log storage.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};

use crate::bindings::_helpers::compute_logs::storage::LocalFilesystemComputeLogStorage;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<LocalFilesystemComputeLogStorage>()
}
