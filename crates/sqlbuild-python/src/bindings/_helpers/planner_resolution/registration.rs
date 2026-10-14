//! Register planner SQL resolution entry points.

use pyo3::prelude::{Bound, PyModule, PyResult};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    super::cursor_bounds::register(module)?;
    super::cursor_model::register(module)?;
    super::cursor_windows::register(module)?;
    super::refs::register(module)?;
    super::locations::register(module)?;
    super::orchestration::register(module)?;
    super::sources::register(module)
}
