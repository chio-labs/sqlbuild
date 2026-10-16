//! Write-hash reconciliation and plan entry construction.

use crate::bindings::_helpers::planner_entries::model_entries::plan_entries;
use crate::bindings::_helpers::planner_entries::models::{PlanEntriesRequest, RelationsRequest};
use crate::bindings::_helpers::planner_entries::relations::planner_relations_context;
use crate::bindings::_helpers::planner_phases::models::{ChangeReconciliation, ModelEntryResults};
use crate::bindings::_helpers::planner_phases::objects::native;
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use pyo3::IntoPyObject;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::PyFrozenSet;

/// The execution scope's changes with honest write hashes, and the actions merged from them.
pub(crate) fn reconcile_execution_changes<'py>(
    (execution_scope, snapshot): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    identities: &Bound<'py, PyAny>,
    resolved_actions: &Bound<'py, PyAny>,
    changes: &Bound<'py, PyAny>,
) -> PyResult<ChangeReconciliation<'py>> {
    let py = execution_scope.py();
    let honest = native(
        py,
        NativeAttr::WithHonestModelWriteHashes,
        &[
            ("scope", execution_scope.clone()),
            ("snapshot", snapshot.clone()),
            ("changes", changes.clone()),
            (
                "version_identities",
                identities.getattr("version_identities")?,
            ),
        ],
    )?;
    let resolved = native(
        py,
        NativeAttr::MergeRecomputedModelChanges,
        &[
            ("resolved_actions", resolved_actions.clone()),
            ("changes", honest.clone()),
        ],
    )?;
    Ok(ChangeReconciliation {
        changes: honest,
        resolved_actions: resolved,
    })
}

fn config_or<'py>(
    config: &Bound<'py, PyAny>,
    path: &[&str],
    fallback: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    if config.is_none() {
        return Ok(fallback);
    }
    let mut value = config.clone();
    for name in path {
        value = value.getattr(*name)?;
    }
    Ok(value)
}

/// Model plan entries for the pruned execution scope, with the freshness and override inputs they need.
pub(crate) fn build_planner_entry_results<'py>(
    (runtime, warehouse): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    (overrides, deferral): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    (execution_scope, reconciliation): (&Bound<'py, PyAny>, &ChangeReconciliation<'py>),
    source_freshness: &Bound<'py, PyAny>,
) -> PyResult<ModelEntryResults<'py>> {
    let py = runtime.py();
    let project = runtime.getattr("project")?;
    let config = runtime.getattr("project_config")?;
    let relations = planner_relations_context(RelationsRequest {
        project: project.clone(),
        adapter: runtime.getattr("adapter")?,
        connection: runtime.getattr("connection")?,
        scope: execution_scope.clone(),
        deferral: deferral.clone(),
        project_config: config.clone(),
        local_config: runtime.getattr("local_config")?,
        known_source_columns: warehouse
            .getattr("inspection_relations")?
            .getattr("source_warehouse_columns")?,
        relation_keys: py.None().into_bound(py),
    })?;
    let propagation = source_freshness.getattr("propagation")?;
    let blocked = if propagation.is_none() {
        PyFrozenSet::empty(py)?.into_any()
    } else {
        propagation.getattr("blocked_model_names")?
    };
    let none = || py.None().into_bound(py);
    let max_override = overrides.getattr("max_microbatches")?;
    let max_microbatches = if max_override.is_none() {
        config_or(&config, &["microbatches", "limits", "max_batches"], none())?
    } else {
        max_override.clone()
    };
    let limit_action = if config.is_none() {
        native(py, RecordId::PlanEntryBuildInputs, &[])?.getattr("microbatch_limit_action")?
    } else {
        config
            .getattr("microbatches")?
            .getattr("limits")?
            .getattr("action")?
    };
    let build_inputs = native(
        py,
        RecordId::PlanEntryBuildInputs,
        &[
            ("source_freshness_blocked_model_names", blocked),
            (
                "external_blocked_model_names",
                PyFrozenSet::new(
                    py,
                    overrides
                        .getattr("external_blocked_model_names")?
                        .try_iter()?
                        .collect::<PyResult<Vec<_>>>()?,
                )?
                .into_any(),
            ),
            (
                "future_cursor_config",
                config_or(&config, &["cursors", "future"], none())?,
            ),
            (
                "start_cursor_config",
                config_or(&config, &["cursors", "start"], none())?,
            ),
            ("invocation_time", runtime.getattr("invocation_time")?),
            ("max_microbatches", max_microbatches),
            (
                "max_microbatches_is_override",
                (!max_override.is_none())
                    .into_pyobject(py)?
                    .to_owned()
                    .into_any(),
            ),
            ("microbatch_limit_action", limit_action),
        ],
    )?;
    plan_entries(PlanEntriesRequest {
        project,
        adapter: runtime.getattr("adapter")?,
        scope: execution_scope.clone(),
        snapshot: warehouse.getattr("snapshot")?,
        relations,
        resolved_models: reconciliation.resolved_actions.getattr("models")?,
        cursor_overrides: overrides.getattr("cursor_overrides")?,
        full_refresh: overrides.getattr("full_refresh")?.is_truthy()?,
        build_inputs,
    })
}
