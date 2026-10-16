//! Register the native warehouse state row functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::state_rows::{
    events, freshness, migration_io, migration_projections, migration_rows, state_tables,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    events::register(module)?;
    freshness::register(module)?;
    migration_rows::register(module)?;
    migration_io::register(module)?;
    migration_projections::register(module)?;
    state_tables::register(module)?;
    Ok(())
}
