//! Per-model full-refresh resolution and full-rebuild refusals.

use crate::bindings::_helpers::planner_phases::constants::FULL_REFRESH_DISABLED_REBUILD_CODE;
use crate::bindings::_helpers::planner_phases::objects::{frozenset, planner_error, strings};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::pyfunction;
use pyo3::types::PyBool;
use sqlbuild_analysis::planner_warehouse::main::full_rebuild_cause::full_rebuild_cause;
use sqlbuild_analysis::planner_warehouse::models::FullRebuildFacts;

fn configured_full_refresh<'py>(model: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    model
        .getattr("config")?
        .getattr("values")?
        .call_method1("get", ("full_refresh",))
}

/// dbt-compatible nullable model full-refresh semantics.
#[pyfunction]
#[pyo3(signature = (*, model, cli_full_refresh))]
pub(crate) fn resolve_model_full_refresh(
    model: &Bound<'_, PyAny>,
    cli_full_refresh: bool,
) -> PyResult<bool> {
    let configured = configured_full_refresh(model)?;
    if configured.is_instance_of::<PyBool>() {
        return configured.extract();
    }
    Ok(cli_full_refresh)
}

/// Names of models effectively full refreshed for this invocation.
#[pyfunction]
#[pyo3(signature = (*, project, cli_full_refresh))]
pub(crate) fn effectively_full_refreshed_model_names<'py>(
    project: &Bound<'py, PyAny>,
    cli_full_refresh: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let mut names: Vec<_> = Vec::new();
    for model in project.getattr("models")?.try_iter()? {
        let model = model?;
        if resolve_model_full_refresh(&model, cli_full_refresh)? {
            names.push(model.getattr("name")?);
        }
    }
    frozenset(project.py(), &names)
}

#[pyfunction]
#[pyo3(signature = (*, change_result, full_refresh))]
pub(crate) fn describe_full_rebuild_cause(
    change_result: &Bound<'_, PyAny>,
    full_refresh: bool,
) -> PyResult<String> {
    Ok(full_rebuild_cause(&FullRebuildFacts {
        full_refresh,
        change_kind: change_result
            .getattr("change_kind")?
            .str()?
            .extract::<String>()?,
        query_changed: change_result.getattr("query_changed")?.is_truthy()?,
        changed_functions: strings(&change_result.getattr("changed_functions")?)?,
        has_schema_findings: change_result.getattr("schema_findings")?.is_truthy()?,
    }))
}

#[pyfunction]
#[pyo3(signature = (*, model, change_result, full_rebuild_cause))]
pub(crate) fn check_full_rebuild_allowed(
    model: &Bound<'_, PyAny>,
    change_result: &Bound<'_, PyAny>,
    full_rebuild_cause: &str,
) -> PyResult<()> {
    let py = model.py();
    if !configured_full_refresh(model)?.is(PyBool::new(py, false)) {
        return Ok(());
    }
    if change_result.getattr("change_kind")?.eq("first_run")?
        || change_result.getattr("query_changed")?.is_truthy()?
    {
        return Ok(());
    }
    let name: String = model.getattr("name")?.extract()?;
    Err(planner_error(
        py,
        &format!(
            "model '{name}' sets full_refresh false, but the plan would fully rebuild it ({full_rebuild_cause})"
        ),
        (
            Some(FULL_REFRESH_DISABLED_REBUILD_CODE),
            Some(
                "set replay_on_change to forward or bounded-<duration> on this model to keep its existing history, or remove full_refresh false to allow the rebuild",
            ),
        ),
    ))
}
