//! Register pure migration helpers.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    super::discovery::register(module)?;
    super::compatibility::register(module)?;
    super::matching::register(module)?;
    super::old_names::register(module)?;
    super::columns::register(module)?;
    super::column_planning::register(module)?;
    super::model_planning::register(module)?;
    super::planning_boundary::register(module)?;
    super::planning_origin::register(module)?;
    super::planning_execution::register(module)?;
    super::projections::register(module)?;
    module.add_class::<super::state_inspection::MigrationStateInspection>()?;
    super::fingerprint::register(module)
}
