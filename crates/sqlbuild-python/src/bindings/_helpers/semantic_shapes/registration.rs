//! Register the native relation shape, coverage and declaration functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::semantic_shapes::{coverage, declarations, shapes};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    shapes::register(module)?;
    coverage::register(module)?;
    declarations::register(module)
}
