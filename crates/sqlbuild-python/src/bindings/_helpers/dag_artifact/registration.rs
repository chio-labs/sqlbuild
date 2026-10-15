//! Register the DAG artifact builder.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::dag_artifact::{artifact, selection};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    artifact::register(module)?;
    selection::register(module)
}
