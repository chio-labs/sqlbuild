//! Computed attributes of the natively hosted project configuration records.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult};

/// `SettingsConfig.sql_validation`: the legacy name of the unified SQL analysis gate.
pub(crate) fn settings_sql_validation(instance: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    Ok(instance.getattr("sql_analysis")?.unbind())
}
