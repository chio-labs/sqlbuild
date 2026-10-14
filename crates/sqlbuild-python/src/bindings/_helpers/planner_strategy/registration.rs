//! Register the planner strategy.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::planner_strategy::{
    audits, cursor_types, lineage, microbatches, strategy,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    audits::register(module)?;
    cursor_types::register(module)?;
    lineage::register(module)?;
    microbatches::register(module)?;
    strategy::register(module)
}
