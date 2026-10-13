//! Register the native dbt event stream.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::dbt_events::stream;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    stream::register(module)
}
