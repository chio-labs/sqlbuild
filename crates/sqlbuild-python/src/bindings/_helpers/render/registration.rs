//! Register the macro call and macro argument functions and classes.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::render::{macro_arguments, macro_calls};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    macro_arguments::register(module)?;
    macro_calls::register(module)?;
    Ok(())
}
