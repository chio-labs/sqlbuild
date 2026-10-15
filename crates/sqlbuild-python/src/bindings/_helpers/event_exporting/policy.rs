//! Lifecycle export policy, severity comparison and narrowing for Python callers.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python, pyfunction,
    wrap_pyfunction,
};
use pyo3::types::{PyDict, PyDictMethods};
use sqlbuild_core::event_export::main::severity_at_least::severity_at_least;
use sqlbuild_core::event_export::main::stricter_severity::stricter_severity;
use sqlbuild_core::event_export::models::{ExportPolicy, ExportSeverity};

use crate::bindings::_helpers::event_exporting::values::{
    export_policy, severity_from, severity_object,
};

const CATALOG_MODULE: &str = "sqlbuild.runtime.observability.constants";

/// `{event_type: (kind, severity, priority)}` for every catalogued lifecycle event, in catalogue order.
#[pyfunction]
fn lifecycle_export_policy_catalog(py: Python<'_>) -> PyResult<Bound<'_, PyDict>> {
    let catalog: Bound<'_, PyAny> = py
        .import(CATALOG_MODULE)?
        .getattr("LIFECYCLE_EVENT_CATALOG")?;
    let policies: Bound<'_, PyDict> = PyDict::new(py);
    for event_type in catalog.try_iter()? {
        let event_type: String = event_type?.extract()?;
        let policy: ExportPolicy = export_policy(py, &event_type)?;
        policies.set_item(
            &event_type,
            (
                policy.kind,
                severity_object(py, policy.severity)?,
                policy.priority,
            ),
        )?;
    }
    Ok(policies)
}

/// Whether a catalogued severity meets a configured minimum.
#[pyfunction]
#[pyo3(signature = (*, severity, minimum))]
fn event_export_severity_at_least(
    severity: &Bound<'_, PyAny>,
    minimum: &Bound<'_, PyAny>,
) -> PyResult<bool> {
    Ok(severity_at_least(
        severity_from(severity)?,
        severity_from(minimum)?,
    ))
}

/// The stricter of a required and an optional minimum severity, as `EventExportSeverity`.
#[pyfunction]
#[pyo3(signature = (*, first, second))]
fn stricter_event_export_severity<'py>(
    first: &Bound<'py, PyAny>,
    second: Option<&Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    let second: Option<ExportSeverity> = second.map(severity_from).transpose()?;
    severity_object(first.py(), stricter_severity(severity_from(first)?, second))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(lifecycle_export_policy_catalog, module)?)?;
    module.add_function(wrap_pyfunction!(event_export_severity_at_least, module)?)?;
    module.add_function(wrap_pyfunction!(stricter_event_export_severity, module)?)
}
