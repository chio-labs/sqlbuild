//! Register the native `sqb freshness` command, observation, planning and state functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::freshness::{
    freshness_command, freshness_observe, observation, planning, state_io,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    freshness_command::register(module)?;
    freshness_observe::register(module)?;
    observation::register(module)?;
    planning::register(module)?;
    state_io::register(module)
}
