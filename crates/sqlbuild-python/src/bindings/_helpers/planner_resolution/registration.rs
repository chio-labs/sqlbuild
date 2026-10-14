//! Register planner SQL resolution entry points.

use pyo3::prelude::{Bound, PyModule, PyResult};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    super::refs::register(module)?;
    super::sources::register(module)
}
