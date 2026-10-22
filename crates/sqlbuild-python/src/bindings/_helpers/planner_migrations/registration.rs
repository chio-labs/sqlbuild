//! Register pure migration helpers.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    super::columns::register(module)?;
    super::column_planning::register(module)?;
    super::projections::register(module)?;
    module.add_class::<super::state_inspection::MigrationStateInspection>()?;
    super::fingerprint::register(module)
}
