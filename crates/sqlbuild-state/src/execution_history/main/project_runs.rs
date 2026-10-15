//! `project_runs`: apply durable event facts in storage order to run projections.

use std::collections::HashMap;

use sqlbuild_core::text::main::python_str_repr::python_str_repr;

use crate::execution_history::constants::{
    DUPLICATE_ORDER, RUN_COMPLETED_EVENT_TYPE, RUN_FAILED_EVENT_TYPE, RUN_STARTED_EVENT_TYPE,
};
use crate::execution_history::errors::{HistoryError, HistoryErrorKind};
use crate::execution_history::models::{ProjectionFact, RunFact, RunRow, RunStatus};

/// Facts sorted by storage order with identical duplicates dropped.
fn unique_ordered(facts: Vec<ProjectionFact>) -> Result<Vec<ProjectionFact>, HistoryError> {
    let mut ordered: Vec<ProjectionFact> = facts;
    ordered.sort_by_key(|fact| fact.storage_order);
    let mut unique: Vec<ProjectionFact> = Vec::with_capacity(ordered.len());
    for fact in ordered {
        if let Some(previous) = unique.last()
            && previous.storage_order == fact.storage_order
        {
            if *previous == fact {
                continue;
            }
            return Err(HistoryError::new(
                HistoryErrorKind::ProjectionConsistency,
                DUPLICATE_ORDER,
            ));
        }
        unique.push(fact);
    }
    Ok(unique)
}

/// The run after one of its events.
fn applied(
    fact: &ProjectionFact,
    run: &RunFact,
    existing: Option<RunRow>,
) -> Result<RunRow, HistoryError> {
    if let Some(existing) = &existing
        && existing.invocation_id != run.invocation_id
    {
        return Err(HistoryError::new(
            HistoryErrorKind::ProjectionConsistency,
            format!(
                "run_id {} has conflicting invocation correlations",
                python_str_repr(&run.run_id)
            ),
        ));
    }
    let base: RunRow = existing.unwrap_or_else(|| RunRow {
        run_id: run.run_id.clone(),
        invocation_id: run.invocation_id.clone(),
        created_at: fact.received_at,
        status: RunStatus::Unknown,
        is_complete: false,
        last_event_cursor: fact.cursor.clone(),
        last_storage_order: fact.storage_order,
        command: None,
        target: None,
        environment: None,
        started_at: None,
        ended_at: None,
    });
    let started_at = if run.event_type == RUN_STARTED_EVENT_TYPE {
        Some(run.occurred_at)
    } else {
        base.started_at
    };
    let (status, is_complete, ended_at) = match run.event_type.as_str() {
        RUN_COMPLETED_EVENT_TYPE => (RunStatus::Completed, true, Some(run.occurred_at)),
        RUN_FAILED_EVENT_TYPE => (RunStatus::Failed, true, Some(run.occurred_at)),
        _ => (base.status, base.is_complete, base.ended_at),
    };
    Ok(RunRow {
        status,
        is_complete,
        started_at,
        ended_at,
        last_event_cursor: fact.cursor.clone(),
        last_storage_order: fact.storage_order,
        ..base
    })
}

/// Current runs updated by every newer run-correlated fact, sorted by `(created_at, run_id)`.
pub fn project_runs(
    facts: Vec<ProjectionFact>,
    current_runs: Vec<RunRow>,
) -> Result<Vec<RunRow>, HistoryError> {
    let mut projected: HashMap<String, RunRow> = current_runs
        .into_iter()
        .map(|run| (run.run_id.clone(), run))
        .collect();
    for fact in unique_ordered(facts)? {
        let Some(run) = &fact.run else {
            continue;
        };
        let next: RunRow = match projected.remove(&run.run_id) {
            Some(existing) if fact.storage_order <= existing.last_storage_order => existing,
            existing => applied(&fact, run, existing)?,
        };
        projected.insert(run.run_id.clone(), next);
    }
    let mut runs: Vec<RunRow> = projected.into_values().collect();
    runs.sort_by(|left, right| {
        (left.created_at, &left.run_id).cmp(&(right.created_at, &right.run_id))
    });
    Ok(runs)
}
