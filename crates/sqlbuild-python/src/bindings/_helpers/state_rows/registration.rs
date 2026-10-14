//! Register the native warehouse state row functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::state_rows::{
    events, freshness, migration_projections, migration_rows,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    events::register(module)?;
    freshness::register(module)?;
    migration_rows::register(module)?;
    migration_projections::register(module)?;
    Ok(())
}
