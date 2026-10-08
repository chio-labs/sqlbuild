//! Register the native column lineage functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::lineage::fast_lineage;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    fast_lineage::register(module)
}
