//! Register the native model analysis session functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::analysis_session::{oracle, query_columns, session};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    session::register(module)?;
    query_columns::register(module)?;
    oracle::register(module)
}
