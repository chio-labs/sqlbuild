//! Register the execution-result documents and the terminal event index.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::result_output::{documents, terminal_index};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    terminal_index::register(module)?;
    documents::register(module)
}
