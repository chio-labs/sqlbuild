//! Register plan entry and plan output assembly entry points.

use pyo3::prelude::{Bound, PyModule, PyResult};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    super::command_plans::register(module)?;
    super::model_entries::register(module)?;
    super::plan_output::register(module)?;
    super::relations::register(module)
}
