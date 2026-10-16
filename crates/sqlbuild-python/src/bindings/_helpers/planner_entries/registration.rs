//! Register plan entry and plan output assembly entry points.

use pyo3::prelude::{Bound, PyModule, PyResult};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    super::clone_plans::register(module)?;
    super::command_plans::register(module)?;
    super::display_plan::register(module)?;
    super::execution_plan::register(module)?;
    super::model_entries::register(module)?;
    super::plan_output::register(module)?;
    super::relations::register(module)?;
    super::test_planning::register(module)
}
