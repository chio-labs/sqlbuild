//! Register the native `sqb freshness` command and its observation entry.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::freshness::{freshness_command, freshness_observe};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    freshness_command::register(module)?;
    freshness_observe::register(module)
}
