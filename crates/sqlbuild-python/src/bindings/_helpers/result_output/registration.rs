//! Register the execution-result documents and the terminal event index.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::result_output::{
    aggregation, documents, event_writer, integration_envelope, resource_ids, terminal_index,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    terminal_index::register(module)?;
    resource_ids::register(module)?;
    aggregation::register(module)?;
    integration_envelope::register(module)?;
    event_writer::register(module)?;
    documents::register(module)
}
