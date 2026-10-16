//! Register the lexical SQL text functions and classes.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::sqltext::{
    code_scanner, ddl_effects, model_headers, placeholders, sql_references,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    model_headers::register(module)?;
    code_scanner::register(module)?;
    sql_references::register(module)?;
    placeholders::register(module)?;
    ddl_effects::register(module)?;
    Ok(())
}
