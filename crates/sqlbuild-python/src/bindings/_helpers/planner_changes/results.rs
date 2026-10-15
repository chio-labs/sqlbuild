//! The planner's Python change-detection result models.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::PyTuple;
use pyo3::{IntoPyObject, PyErr};

use sqlbuild_analysis::planner_changes::errors::UnknownReplayPolicy;
use sqlbuild_analysis::planner_changes::models::{
    Backfill, BackfillAction, ChangeKind, SchemaChangeKind, SchemaColumnSource, SchemaFindingRow,
};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};

pub(crate) const MODELS_MODULE: &str = "sqlbuild.compiler.planner.models";
pub(crate) const TYPES_MODULE: &str = "sqlbuild.compiler.planner.types";
const EXCEPTIONS_MODULE: &str = "sqlbuild.compiler.planner.exceptions";

/// `PlannerInputError(message)` for an unknown replay policy.
pub(crate) fn replay_policy_error(py: Python<'_>, error: UnknownReplayPolicy) -> PyErr {
    match imported(py, EXCEPTIONS_MODULE, "PlannerInputError")
        .and_then(|class| class.call1((error.message(),)))
    {
        Ok(value) => PyErr::from_value(value),
        Err(error) => error,
    }
}

/// `TYPES_MODULE.<enum>(value)`.
pub(crate) fn planner_enum<'py>(
    py: Python<'py>,
    name: &str,
    value: &str,
) -> PyResult<Bound<'py, PyAny>> {
    imported(py, TYPES_MODULE, name)?.call1((value,))
}

/// `BackfillResult(action=..., duration=...)`.
pub(crate) fn backfill_result<'py>(
    py: Python<'py>,
    backfill: &Backfill,
) -> PyResult<Bound<'py, PyAny>> {
    let action: &str = match backfill.action {
        BackfillAction::Full => "full",
        BackfillAction::Bounded => "bounded",
        BackfillAction::ForwardOnly => "forward",
    };
    call_with(
        &imported(py, "sqlbuild._native", "BackfillResult")?,
        &[
            ("action", planner_enum(py, "BackfillAction", action)?),
            (
                "duration",
                backfill.duration.clone().into_pyobject(py)?.into_any(),
            ),
        ],
    )
}

/// The `ChangeKind` member of a decided change.
pub(crate) fn change_kind<'py>(py: Python<'py>, kind: ChangeKind) -> PyResult<Bound<'py, PyAny>> {
    let value: &str = match kind {
        ChangeKind::QueryChanged => "query_changed",
        ChangeKind::FunctionChanged => "function_changed",
        ChangeKind::SchemaChanged => "schema_changed",
        ChangeKind::ConfigChanged => "config_changed",
        ChangeKind::NoChange => "no_change",
    };
    planner_enum(py, "ChangeKind", value)
}

/// A tuple of `SchemaFinding` values.
pub(crate) fn schema_findings<'py>(
    py: Python<'py>,
    findings: &[SchemaFindingRow],
) -> PyResult<Bound<'py, PyTuple>> {
    let class: Bound<'py, PyAny> = imported(py, MODELS_MODULE, "SchemaFinding")?;
    let mut items: Vec<Bound<'py, PyAny>> = Vec::with_capacity(findings.len());
    for finding in findings {
        let kind: &str = match finding.kind {
            SchemaChangeKind::ColumnAdded => "column_added",
            SchemaChangeKind::ColumnRemoved => "column_removed",
            SchemaChangeKind::ColumnTypeChanged => "column_type_changed",
        };
        let source: &str = match finding.source {
            SchemaColumnSource::Yml => "yml",
            SchemaColumnSource::SqlAnalysis => "sql_analysis",
        };
        items.push(call_with(
            &class,
            &[
                ("kind", planner_enum(py, "SchemaChangeKind", kind)?),
                (
                    "column_name",
                    finding.column_name.clone().into_pyobject(py)?.into_any(),
                ),
                ("source", planner_enum(py, "SchemaColumnSource", source)?),
                (
                    "expected_type",
                    finding.expected_type.clone().into_pyobject(py)?.into_any(),
                ),
                (
                    "actual_type",
                    finding.actual_type.clone().into_pyobject(py)?.into_any(),
                ),
            ],
        )?);
    }
    PyTuple::new(py, items)
}
