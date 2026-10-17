//! Computed attributes of the natively hosted project configuration records.

use crate::bindings::_helpers::records::fields::field as native_field;
use pyo3::prelude::{Bound, Py, PyAny, PyResult};

/// `SettingsConfig.sql_validation`: the legacy name of the unified SQL analysis gate.
pub(crate) fn settings_sql_validation(instance: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    Ok(native_field(instance, "sql_analysis")?.unbind())
}
