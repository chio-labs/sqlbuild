//! Direct `#[getter]` reads of this module's native pyclasses, installed into `records::getters`.

use pyo3::IntoPyObjectExt;
use pyo3::prelude::{Bound, PyAny, PyResult, Python};

use crate::bindings::_helpers::records::getters::class_of;
use crate::bindings::_helpers::records::models::GetterEntry;
use crate::bindings::_helpers::rules::early_sql_lint::EarlySqlLint;

/// The getter readers of this module's native pyclasses.
pub(crate) const GETTERS: &[GetterEntry] = &[GetterEntry {
    class: class_of::<EarlySqlLint>,
    read: read_early_sql_lint,
}];

fn read_early_sql_lint<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<EarlySqlLint>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "enabled" => (&this.enabled).into_bound_py_any(py),
        _ => return None,
    })
}
