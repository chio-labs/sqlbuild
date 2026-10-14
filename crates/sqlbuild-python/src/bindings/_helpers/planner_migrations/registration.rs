//! Register pure migration helpers.

use pyo3::prelude::{Bound, PyModule, PyResult};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    super::compatibility::register(module)?;
    super::matching::register(module)?;
    super::old_names::register(module)?;
    super::columns::register(module)?;
    super::column_planning::register(module)?;
    super::model_planning::register(module)?;
    super::projections::register(module)?;
    super::fingerprint::register(module)
}
