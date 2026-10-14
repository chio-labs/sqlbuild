//! Adapt diagnostic display facts while preserving policy and code ordering.

use crate::bindings::_helpers::compile_driver::python_calls::imported;
use crate::bindings::_helpers::planner_migrations::column_warnings::warning;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::PyString;
use sqlbuild_analysis::planner_migrations::main::model_warning::model_warning;
use sqlbuild_analysis::planner_migrations::models::ModelWarning;

pub(super) fn entry_warning<'py>(entry: &Bound<'py, PyAny>) -> PyResult<Option<Bound<'py, PyAny>>> {
    let py = entry.py();
    let name: String = entry.getattr("model_name")?.extract()?;
    let origin = display(&entry.getattr("origin")?)?;
    let destination = display(&entry.getattr("destination")?)?;
    let decision: String = entry.getattr("decision")?.extract()?;
    let completed = entry.getattr("completed_at")?;
    let completed: Option<String> = if completed.is_none() {
        None
    } else {
        Some(completed.call_method0("isoformat")?.extract()?)
    };
    let target: String = entry.getattr("target_label")?.extract()?;
    let policy = entry.getattr("missing_origin_policy")?;
    let remedy: String = imported(
        py,
        "sqlbuild.compiler.planner.constants",
        "HIDDEN_ORIGIN_REMEDY",
    )?
    .extract()?;
    let outcome: String = imported(
        py,
        "sqlbuild.compiler.planner.constants",
        "MISSING_ORIGIN_OUTCOMES",
    )?
    .get_item(&policy)?
    .extract()?;
    let findings: String = PyString::new(py, "; ")
        .call_method1("join", (entry.getattr("compatibility_findings")?,))?
        .extract()?;
    let facts = ModelWarning {
        name: &name,
        origin: &origin,
        destination: &destination,
        decision: &decision,
        manual: entry.getattr("discovery")?.eq("manual")?,
        completed: completed.as_deref(),
        target: &target,
        hidden: entry.getattr("origin_hidden")?.is_truthy()?,
        missing: entry.getattr("origin_missing")?.is_truthy()?,
        deny: policy.eq("deny")?,
        blocked: entry.getattr("blocks_build")?.is_truthy()?,
        remedy: &remedy,
        outcome: &outcome,
        findings: &findings,
    };
    model_warning(&facts)
        .map(|(code, message, error)| warning(entry, code, &message, error))
        .transpose()
}

fn display(location: &Bound<'_, PyAny>) -> PyResult<String> {
    let qualified = location.getattr("qualified_name")?;
    if qualified.is_truthy()? {
        qualified.extract()
    } else {
        location.getattr("name")?.extract()
    }
}
