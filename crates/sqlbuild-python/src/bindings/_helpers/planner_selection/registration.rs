//! Register planner selection bindings.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::planner_selection::{model_selectors, selectors, unit_tests};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    model_selectors::register(module)?;
    selectors::register(module)?;
    unit_tests::register(module)
}
