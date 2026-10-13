//! Register the native column lineage functions and classes.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::lineage::{
    column_lineage_graph, project_lineage, relation_fingerprint, tree_render,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    column_lineage_graph::register(module)?;
    project_lineage::register(module)?;
    relation_fingerprint::register(module)?;
    tree_render::register(module)
}
