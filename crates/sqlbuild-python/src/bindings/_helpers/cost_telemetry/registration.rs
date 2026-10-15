//! Register native run-cost allocation, Snowflake cost collection and statement telemetry.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::cost_telemetry::{allocation, context, ledger, snowflake};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    allocation::register(module)?;
    context::register(module)?;
    ledger::register(module)?;
    snowflake::register(module)
}
