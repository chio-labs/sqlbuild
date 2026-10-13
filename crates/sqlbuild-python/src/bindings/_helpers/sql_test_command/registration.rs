//! Register the native `sqb test` command and its progress labels.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::sql_test_command::test_command;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    test_command::register(module)
}
