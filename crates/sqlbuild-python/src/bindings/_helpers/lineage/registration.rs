//! Register the native column lineage functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::lineage::{fast_lineage, relation_fingerprint, rich_lineage};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    fast_lineage::register(module)?;
    relation_fingerprint::register(module)?;
    rich_lineage::register(module)
}
