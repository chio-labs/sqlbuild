//! Register the native column lineage functions and classes, and `sqb lineage`.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::lineage::{
    column_lineage_graph, lineage_command, project_lineage, relation_fingerprint,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    column_lineage_graph::register(module)?;
    project_lineage::register(module)?;
    relation_fingerprint::register(module)?;
    lineage_command::register(module)
}
