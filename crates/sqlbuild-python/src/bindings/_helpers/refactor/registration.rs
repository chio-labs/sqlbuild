//! Register the native `sqb rename` and `sqb mv` command and its contract-edit helpers.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::refactor::{
    contract_compare, contract_edits, python_strings, refactor_command,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    refactor_command::register(module)?;
    contract_edits::register(module)?;
    contract_compare::register(module)?;
    python_strings::register(module)
}
