//! Register the lexical SQL text functions and classes.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::sqltext::{
    code_scanner, declaration_references, model_headers, placeholders, sql_references, static_sql,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    model_headers::register(module)?;
    code_scanner::register(module)?;
    static_sql::register(module)?;
    sql_references::register(module)?;
    declaration_references::register(module)?;
    placeholders::register(module)?;
    Ok(())
}
