//! Register the native rules, lint and DSL header functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::rules::{dsl_headers, evaluation, lint, skills};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    evaluation::register(module)?;
    lint::register(module)?;
    dsl_headers::register(module)?;
    skills::register(module)
}
