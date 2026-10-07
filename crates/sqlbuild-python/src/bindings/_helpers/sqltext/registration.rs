//! Register the lexical SQL text functions and classes.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::sqltext::{model_headers, sql_references, static_sql};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    model_headers::register(module)?;
    static_sql::register(module)?;
    sql_references::register(module)?;
    Ok(())
}
