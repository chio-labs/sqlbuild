//! Computed attributes of the natively hosted scope records.

use pyo3::IntoPyObjectExt;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult};

/// The completeness sections of a `ScopeCompleteness`.
const COMPLETENESS_SECTIONS: [&str; 6] = [
    "discovery",
    "static_visibility",
    "runtime_usage",
    "relationships",
    "placement",
    "promotion_impact",
];

/// `ScopeCompleteness.complete`: whether every index section is complete.
pub(crate) fn completeness_complete(instance: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let mut complete: bool = true;
    for section in COMPLETENESS_SECTIONS {
        complete = complete && instance.getattr(section)?.is_truthy()?;
    }
    complete.into_py_any(instance.py())
}

/// `ScopeTargetQuery.unknown`: whether the target is absent rather than merely inaccessible.
pub(crate) fn target_query_unknown(instance: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let unknown: bool = !instance.getattr("matches")?.is_truthy()?
        && !instance.getattr("declaration_matches")?.is_truthy()?;
    unknown.into_py_any(instance.py())
}
